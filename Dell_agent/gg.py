import pandas as pd

m = pd.DataFrame()
d = pd.DataFrame([{'a': 11,'b':33}, {'a':78, 'b': 90}])
# print(pd.concat([m,d], ignore_index=True))
a = {'project': {'buffer_dict': {'timestamp': {'instance': {'timestamp': 12345, 'metric': 89}}},
                         'times': ['timestamp']}}
b = {'h': {'q':{'instance': {'u': 1},'insance': {'b': 1}}, 'e': {}, "m": {}, 't': {}}}
c = b['h'].pop('q')
print(list(c.values()))
bb = {"sourceId":"6d30346e-ae28-434d-ac6d-86e6a8cb8300","metricName":"cloud.instance.state","metricId":4088,"sourceType":"RESOURCE","instanceName":"","instanceVal":1,"processThreshHold":False,"contextId":13,"ts":1659693617}
nv={"sourceId":"58f6ff75-1560-47ca-bbbd-7faba27ac0c8","criticalThreshHold":1,"metricName":"availability.down.locations.count","instanceName":"availability.down.locations.count","processThreshHold":True,"contextId":13,"alert_subject":"10.197.10.7 is up.","frequency":60,"loadTh":False,"metricSource":"SYNTHETIC_MONITOR","metricId":6608308,"sourceType":"RESOURCE","warningThreshHold":1,"instanceVal":0,"sourceName":"10.197.10.7","state":0,"ts":1659693622,"repeatCount":1,"alert_desc":"10.197.10.7 is up."}
for key, value in nv.items():
    print(key)
