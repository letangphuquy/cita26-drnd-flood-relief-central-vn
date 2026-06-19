 Okay. Now we do the auditing task. The goal is to audit the decoder/ flow-postprocess or 
  flow preprocess algorithms in Python and make sure they are 100% exact translations.     
  The work process:                                                                        
  - Read the paper main.tex carefully, claims by claims. Focusing on section 3 Proposed    
  Algorithm and section 2. Math Model. Detailing out every details, every steps of the     
  algorithm, the data model, the optimization tricks used. Justification (whys) behind     
  each.                                                                                    
  - Inspect the decoder.hpp implementation carefully, symbol by symbol, function by        
  function, line by line. The main generation loop. The encoder decoder logic. Detailing   
  out everything that was omitted or not presented in main.tex paper.                      
  - Progressively update your insights and belief factually with source citation in a      
  local .md files or audit files. Possibily Create a new sub dir named "docs" under        
  project root, and move the "core-prompts" folder to insdide it. The                      
  audit_algorithm_implementation.md file is in the "docs" folder.                          
  - Next part, spicy and juicy: Audit the Python implementation. Scan function by          
  function, line by line, code path by code path in a scrunity manner similar to when scan 
  C++. Mapping out 1-1 relationship or points out mismatches whenever encountered in the   
  algorithmic flow for decoding decision variables, compared to decoder.hpp. Document all  
  the changes to audit_python_decoder_discrepancies.md                                     
  - Based on the context, draft an educated RFC implementation plan to correct the         
  processor for the visualizer once and for good.                                          
                                                                                           
  DEEP MOTIVATION:                                                                         
  This Mild scenario solution (Knee point solution) uses Land connection from Ly Son       
  island out in the ocean, to inland. And then, only 1 outlier demand point use Water      
  connection although the nodes around it are all used Road connection.                    
  [Image #1]          