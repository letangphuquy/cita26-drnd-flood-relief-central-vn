NOTE: THIS IS OUTDATED.

\mycomment{
UP-NEXT: Experiments
We should re-arrange the below contents to like this (Experiment: HLP benchmarks -- talk both dataset method and exp. set-up, as well as results) (Experiment: Case study -- present dataset methodology, then the settings, then the results) 

4.1 Experimental Set-up (slight modifications)
- Implementation
- Algorithm/ Problem instance parameters
- Performance metric (add cite for HV and IGD)
- Results is averaged from 20 runs, taking mean and stddev value

4.2 Dataset description
Benchmark dataset: Present the method to transform the HLP instances to DRND instances

Central Vietname case study: Present the methodology.

4.3 Experiment 1: Algorithm efficiency 
- Baseline: complete enumeration (can go for branch \& bound approach)
- Proposed: PB-NSGA
- Metrics: HV, IGD, pareto size, algorithm running time.

4.4 Experiment 2: Case study in Vietnam
- Figure: Pareto Front
- Solution visualization on Map
- Insights from the solutions

\section{My draft -- experiments}
\subsection{Experimental Setup}
\begin{itemize}
    \item \textbf{Programming language and machine configuration}. Plan to use the DIMACS 2011 benchmark for machine speed measurement, if space allows.
    \item Algorithm parameters, and parameters for problem instances.
    \item Evaluation metrics. Cite Hypervolume and IGD, and explain briefly in just 1-2 sentences for each
    \item For statistical stability, each experiment is run for 20 times. Then the mean and standard deviation of metric values are recorded. Each run use a consistent random seed per iteration.
\end{itemize}

\subsection{Dataset Description}

\textbf{Benchmark dataset}. As no benchmark dataset is available for the MO-IHLNDP, we transformed HLP benchmarks. We adapt two widely-used hub location benchmarks: the \textbf{AP} set \cite{ap_dataset} (Euclidean instances of sizes 10--100 nodes) and \textbf{TR81} \cite{tr81_dataset} (Turkish inter-city matrix, 81 nodes).
Have a very brief paragraph that summarize the data calibration process (please based on our \`process\_benchmark.py\` file)

% INSERT THE FIGURE CV_Vietnam_Large_with three scenarios

% This snippet should explain the methodology with enough details
\textbf{Synthetic dataset for Central Region} Several coastal cities and provinces at the Central Vietnam, namely Da Nang, Hue, Quang Tri and Quang Ngai are considered. 

\begin{itemize}
\item Coordinates collection
\item Building auxiliary risk matrix
\item Constructing distance and travel time matrix
\item Scenarios generation (epicenter strategy)
\item Large instance and Small instance
\item What's more?
\end{itemize}

\subsection{Experiment 1: Algorithms benchmarking}
\begin{itemize}
    \item Dataset: Standard benchmark dataset (HLP -> DRND)
    \item Compare the proposed algorithm against complete enumeration technique (speed up with branch and bound solver). Prove that the PG-NSGA produces optimal results for small instance
    \item Stress-testing (measuring runnning time in seconds) and showcasing algorithm's efficiency 
\end{itemize}

\subsection{Experiment 2: Case study in Vietnam}
\begin{itemize}
    \item Dataset: Our synthetic dataset. Only run the proposed algorithm on the dataset.
    \item Sensitivity analysis. How does the solution structure change between different scenarios.
    \item Managerial insights
\end{itemize}

The figures that need to be inserted:
\begin{itemize}
    \item Pareto front (used for trade-off analysis)
    \item Solutions found by the algorithm, plotted on the Vietnamese map. What are the implications and managerial insights?
    \item Do a slight sensitivity analysis from the same figure (solution visualized on map)
\end{itemize}

}