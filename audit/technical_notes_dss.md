# Technical Notes — DSS Visualizer

## Issue: Pareto Chart Point Click Selection Not Working

**Context:** `st.plotly_chart(..., on_select="rerun", selection_mode="points")` in Streamlit 1.58.  
**Symptom:** Clicking a blue dot on the Pareto front had no effect — no star movement, no map reload.

---

## Wrong Guesses (Chronological)

### 1. `dragmode=False` strips Plotly drag handlers
**Tried:** Setting `dragmode=False` to prevent pan/zoom.  
**Wrong because:** Plotly.js strips `__onmousedown`/`__onmouseup` from the `nsewdrag` SVG rect when dragmode is False, preventing all click detection. Removed it.

### 2. Checking `__onmousedown` on `rect.nsewdrag` as a health signal
**Tried:** Using `'__onmousedown' in rect` in JS to verify drag handlers were attached.  
**Wrong because:** Plotly uses D3's event binding (via `d3.select().on()`), which does NOT set `element.__onmousedown`. Only legend toggle rects (indices 18/19) use the `__onmousedown` property pattern. The main drag rect always showed `hasMD: false` regardless of configuration — the check was invalid.

### 3. `fixedrange=True` alone (without explicit dragmode)
**Tried:** `fig.update_xaxes(fixedrange=True); fig.update_yaxes(fixedrange=True)` to lock axes.  
**Result:** Chart entered "pointer-click" mode (`cursor-pointer` on nsewdrag). Clicking fired `plotly_click` only — NOT `plotly_selected`. Streamlit's `on_select` listens to `plotly_selected`, so no rerun triggered.

### 4. `clickmode="event+select"` in Python only
**Tried:** `fig.update_layout(clickmode="event+select")`.  
**Wrong because:** Streamlit's frontend **overrides** `clickmode` to `"event"` after calling `Plotly.react()` — confirmed by checking `div._fullLayout.clickmode` in JS, which always showed `"event"` regardless of what Python set. The Python-side `clickmode` is silently discarded.

### 5. `dragmode="select"` + `fixedrange=True` (both together, no clickmode patch)
**Tried:** Both settings applied in Python.  
**Result:** `cursor-pointer` mode. Click showed visual point highlight (`plotly_click` fired) but `plotly_selected` did NOT fire → no rerun. User confirmed: "point is selected but the marker does not mark."

### 6. `dragmode="select"` without `fixedrange`
**Tried:** Removed fixedrange, kept dragmode.  
**Result:** `cursor-crosshair` (true select/drag mode). In this mode, **only dragging** (drawing a selection box) fires `plotly_selected`. A single **click** without drag fires only `plotly_click` when `clickmode="event"` (Streamlit's override). User confirmed: "nothing happens."

### 7. Simulating clicks via JS `div._ev.emit('plotly_selected', ...)`
**Tried:** Manually emitting `plotly_selected` on the Plotly EventEmitter from JS.  
**Wrong because:** Streamlit's frontend handler IS called (confirmed via listener wrapping), but it does NOT trigger a backend rerun when the event comes from `emit()`. Streamlit appears to validate event source context (WebSocket pathway) or checks internal Plotly state beyond the event data.

### 8. `customdata[0]` for index extraction
**Tried:** `int(pts[0].customdata[0])` to read the clicked point's index.  
**Wrong for two reasons:**
- Streamlit returns `event.selection.points` as a **list of plain dicts**, not attribute-accessible objects. `pts[0].customdata` raises `AttributeError`.
- Even with dict access `pts[0]["customdata"]`, this approach is fragile because Streamlit may flatten nested customdata unexpectedly.

---

## Root Causes (Confirmed)

1. **Streamlit overrides `clickmode` to `"event"`** after every `Plotly.react()` call. This makes single point clicks emit `plotly_click` only — not `plotly_selected`. Since `on_select` listens to `plotly_selected`, clicks never trigger reruns.

2. **`fixedrange=True` + `dragmode="select"` does NOT disable `plotly_selected`** — it only disables pan/zoom. The combination still allows Plotly to emit `plotly_selected` IF `clickmode` is properly set to `"event+select"`.

3. **Selection points are plain dicts**, not objects. All attribute access (`pt.curve_number`) must be dict access (`pt["curve_number"]`).

---

## Working Solution

### Python (app.py)

```python
fig.update_layout(dragmode="select")
fig.update_xaxes(fixedrange=True)
fig.update_yaxes(fixedrange=True)
event = st.plotly_chart(fig, on_select="rerun", selection_mode="points",
                        key="pareto_chart", use_container_width=True)
for _pt in (event.selection.points or []):
    if _pt["curve_number"] == 0 and _pt["point_number"] != sel_idx:
        st.session_state["selected_idx"] = _pt["point_number"]
        st.rerun()
```

**Key points:**
- `dragmode="select"` puts Plotly in selection mode
- `fixedrange=True` prevents accidental pan/zoom while preserving selection event emission
- Handler mirrors the working Z1/Z2/Knee buttons exactly: update `session_state`, call `st.rerun()`
- `pt["curve_number"] == 0` filters to the Pareto front trace only (ignores the selected-star overlay at trace index 1)
- `pt["point_number"]` is the direct index of the clicked point in the Pareto front array — no customdata needed

### JavaScript (FAB iframe, persistent poller)

Streamlit overrides `clickmode` to `"event"` after every rerun. A 350ms poller in the FAB `st.components.v1.html()` iframe restores it:

```javascript
(function patch() {
    var pW = window.parent;
    var Plotly = pW.Plotly;
    if (Plotly) {
        pW.document.querySelectorAll('.js-plotly-plot').forEach(function(d) {
            if (d._fullLayout && d._fullLayout.dragmode === 'select'
                    && d._fullLayout.clickmode !== 'event+select') {
                Plotly.relayout(d, {clickmode: 'event+select'});
            }
        });
    }
    setTimeout(patch, 350);
})();
```

**Why this works:**
- `Plotly` IS available as a global on the parent page (`window.parent.Plotly`)
- `Plotly.relayout(div, {clickmode: 'event+select'})` fires `plotly_relayout` but does NOT trigger a Streamlit rerun (only `plotly_selected` triggers reruns for `on_select` charts)
- The FAB iframe persists across Streamlit reruns (content unchanged = iframe not remounted), so the `setTimeout` chain keeps running indefinitely
- After each Streamlit rerun resets `clickmode` to `"event"`, the poller fires within 350ms and restores `"event+select"`
- With `clickmode="event+select"` active, a single point click emits BOTH `plotly_click` AND `plotly_selected` → Streamlit's `on_select` handler catches `plotly_selected` → triggers backend rerun

### Why the sidebar chart uses the same fix

The sidebar mini-Pareto (`key="pareto_sidebar"`) uses the identical pattern. Both charts share the same Streamlit-override problem, same JS fix, same dict-based Python handler.

---

## Diagnosis Tools Used

- `div._fullLayout.clickmode` — read actual runtime clickmode (not what Python set)
- `div._fullLayout.dragmode` — confirm drag mode
- `div.querySelector('rect.nsewdrag').className.baseVal` — `cursor-pointer` = pointer mode, `cursor-crosshair` = true select mode
- `Object.keys(div._ev._events)` — list all Plotly events Streamlit has registered listeners for
- Wrapping `div._ev._events['plotly_selected']` listeners to confirm they fire but checking if a Streamlit rerun actually happens
- `Plotly.relayout(div, {clickmode: 'event+select'})` directly from Chrome DevTools to test before automating
