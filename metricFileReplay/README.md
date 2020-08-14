# InsightAgent: MetricFileReplay
Agent Type: MetricFileReplay
Platform: Linux, Python 2.7 or Python 3.5+

InsightFinder accepts metric data in a csv file with the following format: There must be a timestamp field (specified in Unix epoch (ms)); the other columns are metric values for that timestamp. The column name in the csv file follows the format of "timestamp" or metricName[instanceName] or metricName[containerName_instanceName]. The metric name should not include special characters such as "[]", " ", ":". A sample metric data snippet is provided as follows,


```csv
timestamp, cpu[node1],memory[node1],disk_read[node1],disk_write[node1],network_receive[node1],network_send[node1], cpu[node2],memory[node2],disk_read[node2],disk_write[node2],network_receive[node2],network_send[node2], cpu[node3],memory[node3],disk_read[node3],disk_write[node3],network_receive[node3],network_send[node3], cpu[node4],memory[node4],disk_read[node4],disk_write[node4],network_receive[node4],network_send[node4], cpu[node5],memory[node5],disk_read[node5],disk_write[node5],network_receive[node5],network_send[node5]
1442853541000,0.3085915,1609.3184,0.0,0.0,0.837,0.874,0.2850924,1484.668928,0.0,0.0,1.086,1.032,0.3057226,1433.305088,0.0,0.0,0.852,0.825,0.196377,1511.743488,0.0,0.0,0.792,0.85,0.2577666,1405.263872,0.0,0.0,1.087,1.073
1442853603000,9.2856282,1575.559168,1.871872,0.0,57.345,53.9,4.241061,1518.252032,1.701888,0.0,9.415,8.858,3.7213078,1453.44512,1.486848,0.0,8.539,6.583,2.5453482,1533.444096,1.314816,0.0,5.816,5.044,3.8383389,1424.785408,2.246656,0.008192,7.054,6.543
1442853664000,10.6987477,1569.644544,2.234368,0.0,69.533,65.395,4.5311237,1544.613888,1.261568,0.0,12.139,9.662,3.9747478,1454.215168,2.279424,0.0,8.685,8.116,3.0986336,1532.424192,1.509376,0.0,6.627,5.518,3.9514771,1424.150528,3.037184,0.0,11.097,9.077
1442853726000,7.9018865,1574.473728,1.705984,0.0,68.801,63.758,3.1633041,1547.845632,2.51904,0.0,10.923,9.507,3.0656052,1451.302912,2.159957,0.0,10.292,8.462,2.3085119,1532.678144,2.050048,0.0,6.945,5.792,3.4080159,1418.747904,2.674688,0.0,8.052,7.899
1442853789000,10.6617469,1571.045376,1.338026,0.0,46.969,44.163,4.0055244,1550.823424,0.789162,0.0,7.843,6.431,4.6800373,1446.866944,2.65216,0.0,10.984,9.6,3.6261394,1533.988864,1.630208,0.0,5.226,4.695,4.2490901,1420.849152,1.878698,0.0,5.79,5.783
```


