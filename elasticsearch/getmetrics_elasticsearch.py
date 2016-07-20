#!/usr/bin/python

import urllib2
import json
import time
import os
from optparse import OptionParser
import socket

'''
this script gathers system info from elastic search and add to daily csv file
'''

usage = "Usage: %prog [options]"
parser = OptionParser(usage=usage)
parser.add_option("-d", "--directory",
    action="store", dest="homepath", help="Directory to run from")
(options, args) = parser.parse_args()


if options.homepath is None:
    homepath = os.getcwd()
else:
    homepath = options.homepath
datadir = 'data/'

esNodeUrl = "http://localhost:9200/_nodes/_local/stats/transport,http,process,jvm,indices,thread_pool"
esClusterUrl = "http://localhost:9200/_cluster/health"
esIndexUrl = "http://localhost:9200/_all/_stats"
esInfo = "http://localhost:9200/_nodes/_local"

AllMetricDict = {}
AllMetricList = []
timestamp = int(round(time.time() * 1000))
AllMetricList.append("timestamp")
AllMetricDict["timestamp"] = timestamp
date = time.strftime("%Y%m%d")
hostname = socket.gethostname().partition(".")[0]
deltaFields = ["TotalIndexRequestsPerNode", "TotalMerges", "TotalQueryTime", "TotalSearchRequestsPerNode", "GarbageCollectorTime", "TotalSearchRequestsPerCluster"]
newResult = {}
previousResult = {}
firstresult = False

NodeDict = {
"TotalGetRequests": "nodes.%s.indices.get.total",
"TotalIndexRequestsPerNode": "nodes.%s.indices.indexing.index_total",
"TotalMerges": "nodes.%s.indices.merges.total",
"TotalQueryTime": "nodes.%s.indices.search.query_time_in_millis",
"TotalSearchRequestsPerNode": "nodes.%s.indices.search.query_total",
"GarbageCollectorTime": "nodes.%s.jvm.gc.collectors.young.collection_time_in_millis",
"NumberOfDocumentsInNode": "nodes.%s.indices.docs.count",
"NumberOfDeletedDocuments": "nodes.%s.indices.docs.deleted",
"CurrentMerges": "nodes.%s.indices.merges.current",
"NumberOfSegments": "nodes.%s.indices.segments.count",
"CommittedHeap": "nodes.%s.jvm.mem.heap_committed_in_bytes",
"UsedHeap": "nodes.%s.jvm.mem.heap_used_in_bytes",
"NumberOfOpenFileDescriptors": "nodes.%s.process.open_file_descriptors",
"ProcessCpuPercent": "nodes.%s.process.cpu.percent",
"RejectedBulkRequests": "nodes.%s.thread_pool.bulk.rejected",
"RejectedFlushRequests": "nodes.%s.thread_pool.flush.rejected",
"RejectedGenericRequests": "nodes.%s.thread_pool.generic.rejected",
"RejectedGetRequests": "nodes.%s.thread_pool.get.rejected",
"RejectedIndexRequests": "nodes.%s.thread_pool.index.rejected",
"RejectedForceMergeRequests": "nodes.%s.thread_pool.force_merge.rejected",
"RejectedRefreshRequests": "nodes.%s.thread_pool.refresh.rejected",
"RejectedSearchRequests": "nodes.%s.thread_pool.search.rejected",
"RejectedSnapshotRequests": "nodes.%s.thread_pool.snapshot.rejected",
"IndicesStoreThrottleTime": "nodes.%s.indices.store.throttle_time_in_millis",
"IndicesSearchOpenContexts": "nodes.%s.indices.search.open_contexts",
"IndicesCacheFieldEviction": "nodes.%s.indices.fielddata.evictions",
"IndicesCacheFieldSize": "nodes.%s.indices.fielddata.memory_size_in_bytes",
"JvmgcCount": "nodes.%s.jvm.gc.collectors.young.collection_count",
"JvmgcOldTime": "nodes.%s.jvm.gc.collectors.old.collection_time_in_millis",
"JvmgcOldCount": "nodes.%s.jvm.gc.collectors.old.collection_count",
"IndicesFlushTotal": "nodes.%s.indices.flush.total",
"IndicesFlushTime": "nodes.%s.indices.flush.total_time_in_millis",
"IndicesMergesCurrentDocs": "nodes.%s.indices.merges.current_docs",
"IndicesMergesCurrentSize": "nodes.%s.indices.merges.current_size_in_bytes",
"IndicesMergesTotalDocs": "nodes.%s.indices.merges.total_docs",
"IndicesMergesTotalSize": "nodes.%s.indices.merges.total_size_in_bytes",
"IndicesMergesTime": "nodes.%s.indices.merges.total_time_in_millis",
"IndicesRefreshTotal": "nodes.%s.indices.refresh.total",
"IndicesRefreshTime": "nodes.%s.indices.refresh.total_time_in_millis",
"IndicesSegmentsSize": "nodes.%s.indices.segments.memory_in_bytes",
"IndicesSegmentsIndexWriterMaxSize": "nodes.%s.indices.segments.index_writer_max_memory_in_bytes",
"IndicesSegmentsIndexWriterSize": "nodes.%s.indices.segments.index_writer_memory_in_bytes",
"IndicesStoreSize": "nodes.%s.indices.store.size_in_bytes",
"IndicesIndexingIndexTime": "nodes.%s.indices.indexing.index_time_in_millis",
"IndicesIndexingDeleteTotal": "nodes.%s.indices.indexing.delete_total",
"IndicesIndexingDeleteTime": "nodes.%s.indices.indexing.delete_time_in_millis",
"IndicesIndexingIndexCurrent": "nodes.%s.indices.indexing.index_current",
"IndicesIndexingDeleteCurrent": "nodes.%s.indices.indexing.delete_current",
"IndicesGetTime": "nodes.%s.indices.get.time_in_millis",
"IndicesGetExistsTotal": "nodes.%s.indices.get.exists_total",
"IndicesGetExistsTime": "nodes.%s.indices.get.exists_time_in_millis",
"IndicesGetMissingTotal": "nodes.%s.indices.get.missing_total",
"IndicesGetMissingTime": "nodes.%s.indices.get.missing_time_in_millis",
"IndicesGetCurrent": "nodes.%s.indices.get.current",
"IndicesSearchQueryCurrent": "nodes.%s.indices.search.query_current",
"IndicesSearchFetchCurrent": "nodes.%s.indices.search.fetch_current",
"IndicesSearchFetchTotal": "nodes.%s.indices.search.fetch_total",
"IndicesSearchFetchTime": "nodes.%s.indices.search.fetch_time_in_millis",
"JvmMemHeapUsedPercent": "nodes.%s.jvm.mem.heap_used_percent",
"JvmMemNonHeapCommitted": "nodes.%s.jvm.mem.non_heap_committed_in_bytes",
"JvmMemNonHeapUsed": "nodes.%s.jvm.mem.non_heap_used_in_bytes",
"JvmMemPoolsYoungMaxinBytes": "nodes.%s.jvm.mem.pools.young.max_in_bytes",
"JvmMemPoolsYoungUsedinBytes": "nodes.%s.jvm.mem.pools.young.used_in_bytes",
"JvmMemPoolsOldMaxinBytes": "nodes.%s.jvm.mem.pools.old.max_in_bytes",
"JvmMemPoolsOldUsedinBytes": "nodes.%s.jvm.mem.pools.old.used_in_bytes",
"JvmUptime": "nodes.%s.jvm.uptime_in_millis",
"JvmThreadsCount": "nodes.%s.jvm.threads.count",
"JvmThreadsPeak": "nodes.%s.jvm.threads.peak_count",
"TransportServerOpen": "nodes.%s.transport.server_open",
"TransportRxCount": "nodes.%s.transport.rx_count",
"TransportRxSize": "nodes.%s.transport.rx_size_in_bytes",
"TransportTxCount": "nodes.%s.transport.tx_count",
"TransportTxSize": "nodes.%s.transport.tx_size_in_bytes",
"HttpCurrentOpen": "nodes.%s.http.current_open",
"HttpTotalOpen": "nodes.%s.http.total_opened"
}

IndexDict = {
"TotalSearchRequestsPerCluster": "total.search.query_total",
"TotalIndexRequestsPerCluster": "total.indexing.index_total",
"FieldDataSize": "total.fielddata.memory_size_in_bytes",
"NumberOfMerges": "total.merges.total",
"NumberOfDocumentsInCluster": "total.docs.count",
"IndicesPrimariesTranslogSize": "primaries.translog.size_in_bytes",
"IndicesPrimariesTranslogOperations": "primaries.translog.operations",
"IndicesPrimariesSegmentsMemory": "primaries.segments.memory_in_bytes",
"IndicesPrimariesSegmentsCount": "primaries.segments.count",
"IndicesPrimariesFlushTotal": "primaries.flush.total",
"IndicesPrimariesFlushTotalTime": "primaries.flush.total_time_in_millis",
"IndicesPrimariesWarmerTotalPrimariesWarmerTotaltime": "primaries.warmer.total_time_in_millis",
"IndicesPrimariesWarmerTotal": "primaries.warmer.total",
"IndicesPrimariesWarmerCurrent": "primaries.warmer.current",
"IndicesPrimariesFielddataMemorySize": "primaries.fielddata.memory_size_in_bytes",
"IndicesPrimariesFielddataEvictions": "primaries.fielddata.evictions",
"IndicesPrimariesRefreshTotalTime": "primaries.refresh.total_time_in_millis",
"IndicesPrimariesRefreshTotal": "primaries.refresh.total",
"IndicesPrimariesMergesTotalDocs": "primaries.merges.total_docs",
"IndicesPrimariesMergesTotalSize": "primaries.merges.total_size_in_bytes",
"IndicesPrimariesMergesCurrent": "primaries.merges.current",
"IndicesPrimariesMergesTotal": "primaries.merges.total",
"IndicesPrimariesMergesCurrentDocs": "primaries.merges.current_docs",
"IndicesPrimariesMergesTotalTime": "primaries.merges.total_time_in_millis",
"IndicesPrimariesMergesCurrentSize": "primaries.merges.current_size_in_bytes",
"IndicesPrimariesCompletionSize": "primaries.completion.size_in_bytes",
"IndicesPrimariesPercolateTotal": "primaries.percolate.total",
"IndicesPrimariesPercolateMemorySize": "primaries.percolate.memory_size_in_bytes",
"IndicesPrimariesPercolateQueries": "primaries.percolate.queries",
"IndicesPrimariesPercolateTime": "primaries.percolate.time_in_millis",
"IndicesPrimariesPercolateCurrent": "primaries.percolate.current",
"IndicesPrimariesDocsCount": "primaries.docs.count",
"IndicesPrimariesDocsDeleted": "primaries.docs.deleted",
"IndicesPrimariesStoreSize": "primaries.store.size_in_bytes",
"IndicesPrimariesStoreThrottleTime": "primaries.store.throttle_time_in_millis",
"IndicesPrimariesIndexingIndexTotal": "primaries.indexing.index_total",
"IndicesPrimariesIndexingIndexTime": "primaries.indexing.index_time_in_millis",
"IndicesPrimariesIndexingIndexCurrent": "primaries.indexing.index_current",
"IndicesPrimariesIndexingDeleteTotal": "primaries.indexing.delete_total",
"IndicesPrimariesIndexingDeleteTime": "primaries.indexing.delete_time_in_millis",
"IndicesPrimariesIndexingDeleteCurrent": "primaries.indexing.delete_current",
"IndicesPrimariesGetTime": "primaries.get.time_in_millis",
"IndicesPrimariesGetExistsTotal": "primaries.get.exists_total",
"IndicesPrimariesGetExistsTime": "primaries.get.exists_time_in_millis",
"IndicesPrimariesGetMissingTotal": "primaries.get.missing_total",
"IndicesPrimariesGetMissingTime": "primaries.get.missing_time_in_millis",
"IndicesPrimariesGetCurrent": "primaries.get.current",
"IndicesPrimariesSearchOpenContexts": "primaries.search.open_contexts",
"IndicesPrimariesSearchQueryTotal": "primaries.search.query_total",
"IndicesPrimariesSearchQueryTime": "primaries.search.query_time_in_millis",
"IndicesPrimariesSearchQueryCurrent": "primaries.search.query_current",
"IndicesPrimariesSearchFetchTotal": "primaries.search.fetch_total",
"IndicesPrimariesSearchFetchTime": "primaries.search.fetch_time_in_millis",
"IndicesPrimariesSearchFetchCurrent": "primaries.search.fetch_current",
"IndicesTotalDocsDeleted": "total.docs.deleted",
"IndicesTotalStoreSize": "total.store.size_in_bytes",
"IndicesTotalStoreThrottleTime": "total.store.throttle_time_in_millis",
"IndicesTotalIndexingIndexTime": "total.indexing.index_time_in_millis",
"indicesTotalIndexingIndexCurrent": "total.indexing.index_current",
"indicesTotalIndexingDeleteTotal": "total.indexing.delete_total",
"indicesTotalIndexingDeleteTime": "total.indexing.delete_time_in_millis",
"indicesTotalIndexingDeleteCurrent": "total.indexing.delete_current",
"indicesTotalGetTotal": "total.get.total",
"indicesTotalGetTime": "total.get.time_in_millis",
"indicesTotalGetExistsTotal": "total.get.exists_total",
"IndicesTotalGetExistsTime": "total.get.exists_time_in_millis",
"IndicesTotalGetMissingTotal": "total.get.missing_total",
"IndicesTotalGetMissingTime": "total.get.missing_time_in_millis",
"IndicesTotalGetCurrent": "total.get.current",
"IndicesTotalSearchOpenContexts": "total.search.open_contexts",
"IndicesTotalSearchQueryTime": "total.search.query_time_in_millis",
"IndicesTotalSearchQueryCurrent": "total.search.query_current",
"IndicesTotalSearchFetchTotal": "total.search.fetch_total",
"IndicesTotalMergesTotalDocs": "total.merges.total_docs",
"IndicesTotalMergesTotalSize": "total.merges.total_size_in_bytes",
"IndicesTotalMergesCurrent": "total.merges.current",
"IndicesTotalMergesCurrentDocs": "total.merges.current_docs",
"IndicesTotalMergesTotalTime": "total.merges.total_time_in_millis",
"IndicesTotalMergesCurrentSize": "total.merges.current_size_in_bytes",
"IndicesTotalFielddataEvictions": "total.fielddata.evictions"
}

elkGroupIndex = 6035
groupIDRecord = {}

def getindex(col_name):
    global elkGroupIndex
    global groupIDRecord
    if col_name in groupIDRecord:
        return groupIDRecord[col_name]
    else:
        if col_name == "NumberOfNodes":
            returnid = 6001
        elif col_name == "NumberOfDataNodes":
            returnid = 6002
        elif col_name == "NumberOfActivePrimaryShards":
            returnid = 6003
        elif col_name == "NumberOfActiveShards":
            returnid = 6004
        elif col_name == "NumberOfRelocatingShards":
            returnid = 6005
        elif col_name == "NumberOfInitializingShards":
            returnid = 6006
        elif col_name == "NumberOfUnAssignedShards":
            returnid = 6007
        elif col_name == "TotalGetRequests":
            returnid = 6008
        elif col_name == "TotalIndexRequestsPerNode":
            returnid = 6009
        elif col_name == "TotalMerges":
            returnid = 6010
        elif col_name == "TotalQueryTime":
            returnid = 6011
        elif col_name == "TotalSearchRequestsPerNode":
            returnid = 6012
        elif col_name == "GarbageCollectorTime":
            returnid = 6013
        elif col_name == "NumberOfDocumentsInNode":
            returnid = 6014
        elif col_name == "NumberOfDeletedDocuments":
            returnid = 6015
        elif col_name == "CurrentMerges":
            returnid = 6016
        elif col_name == "NumberOfSegments":
            returnid = 6017
        elif col_name == "CommittedHeap":
            returnid = 6018
        elif col_name == "UsedHeap":
            returnid = 6019
        elif col_name == "NumberOfOpenFileDescriptors":
            returnid = 6020
        elif col_name == "ProcessCpuPercent":
            returnid = 6021
        elif col_name == "RejectedBulkRequests":
            returnid = 6022
        elif col_name == "RejectedFlushRequests":
            returnid = 6023
        elif col_name == "RejectedGenericRequests":
            returnid = 6024
        elif col_name == "RejectedGetRequests":
            returnid = 6025
        elif col_name == "RejectedIndexRequests":
            returnid = 6026
        elif col_name == "RejectedForceMergeRequests":
            returnid = 6027
        elif col_name == "RejectedRefreshRequests":
            returnid = 6028
        elif col_name == "RejectedSearchRequests":
            returnid = 6029
        elif col_name == "RejectedSnapshotRequests":
            returnid = 6030
        elif col_name == "TotalSearchRequestsPerCluster":
            returnid = 6031
        elif col_name == "TotalIndexRequestsPerCluster":
            returnid = 6032
        elif col_name == "FieldDataSize":
            returnid = 6033
        elif col_name == "NumberOfMerges":
            returnid = 6034
        elif col_name == "NumberOfDocumentsInCluster":
            returnid = 6035
        else:      
            elkGroupIndex+=1
            returnid = elkGroupIndex
        groupIDRecord[col_name] = returnid
        return returnid

def writeToCsv():
    global AllMetricDict
    global AllMetricList
    log = ""
    fields = ""
    resource_usage_file = open(os.path.join(homepath,datadir+date+".csv"),'a+')
    csvContent = resource_usage_file.readlines()
    numlines = len(csvContent)
    for metric in AllMetricList:
        if log != "":
            log = log + ","
        if fields != "":
            fields = fields + ","
        log = log + str(AllMetricDict[metric])
        fields = fields + str(metric)
    if numlines < 1:
        resource_usage_file.write("%s\n"%(fields))
    else:
        headercsv = csvContent[0]
        header = headercsv.split("\n")[0].split(",")
        fieldList = fields.split(",")
        if cmp(header,fieldList) != 0:
            oldFile = os.path.join(homepath,datadir+date+".csv")
            newFile = os.path.join(homepath,datadir+date+"."+time.strftime("%Y%m%d%H%M%S")+".csv")
            os.rename(oldFile,newFile)
            resource_usage_file = open(os.path.join(homepath,datadir+date+".csv"), 'a+')
            resource_usage_file.write("%s\n"%(fields))
    resource_usage_file.write("%s\n"%(log))
    resource_usage_file.flush()
    resource_usage_file.close()

def getJson(url):
    request = urllib2.Request(url)
    response = urllib2.urlopen(request, timeout=10)
    return json.load(response)

def getClusterName(jsondata):
    return jsondata['cluster_name']

def getClusterInfo():
    global AllMetricList
    global AllMetricDict
    clusterDict = {}
    jsonContent = getJson(esClusterUrl)
    #clusterDict = {"ClusterName": ["cluster_name"], "ClusterStatus": ["status"], "Nodes": ["number_of_nodes"], "DataNodes": ["number_of_data_nodes"], \
    clusterDict = {"NumberOfNodes": ["number_of_nodes"], "NumberOfDataNodes": ["number_of_data_nodes"], \
    "NumberOfActivePrimaryShards": ["active_primary_shards"], "NumberOfActiveShards": ["active_shards"], "NumberOfRelocatingShards": ["relocating_shards"], \
    "NumberOfInitializingShards": ["initializing_shards"], "NumberOfUnAssignedShards": ["unassigned_shards"]}
    for keyName in sorted(clusterDict):
        key = keyName+"["+hostname+"]:" + str(getindex(keyName))
        AllMetricDict[key] = abs(reduce(lambda x,y: x[y], clusterDict[keyName], jsonContent))
        AllMetricList.append(key)

def getNodeInfo():
    global NodeDict
    global AllMetricList
    global AllMetricDict
    global newResult
    global deltaFields
    global previousResult
    jsonContent = getJson(esNodeUrl)
    NodeStats = {}
    for node in sorted(jsonContent['nodes'].keys()):
        nodeName = jsonContent['nodes'][node]['name']
        for keyName in NodeDict:
            converttoMB = False
            key = keyName+"["+hostname+"_"+nodeName+"]:" + str(getindex(keyName))
            values = NodeDict[keyName] %node
            if "bytes" in values:
                converttoMB = True
            values = values.split(".")
            AllMetricList.append(key)
            result = reduce(lambda x,y: x[y], values, jsonContent)
            if converttoMB == True:
                result = float(float(result)/(1024*1024))
            if key.split("[")[0] in deltaFields and firstresult == False:
                 newResult[key] = abs(result)
                 if key not in previousResult:
                     result = 0
                 else:
                     result = result - float(previousResult[key])
            AllMetricDict[key] = abs(result)

def getIndexInfo():
    global IndexDict
    global AllMetricList
    global AllMetricDict
    global newResult
    global deltaFields
    global previousResult
    jsonContent = getJson(esIndexUrl)
    indexCount = "Indices["+hostname+"]:" + str(getindex("Indices"))
    AllMetricList.append(indexCount)
    AllMetricDict[indexCount] = len(jsonContent['indices'].keys())    
    for indicesName in sorted(jsonContent['indices'].keys()):
        for keyName in IndexDict:
            converttoMB = False
            if "bytes" in IndexDict[keyName]:
                converttoMB = True
            values = IndexDict[keyName].split(".")
            key = keyName + "[" + hostname + "_" + indicesName + "]:" + str(getindex(keyName))
            AllMetricList.append(key)
            result = reduce(lambda x,y: x[y], values, jsonContent['indices'][indicesName])
            if converttoMB == True:
                result = float(float(result)/(1024*1024))
            if key.split("[")[0] in deltaFields and firstresult == False:
                 newResult[key] = abs(result)
                 if key not in previousResult:
                     result = 0
                 else:
                     result = result - float(previousResult[key])
            AllMetricDict[key] = abs(result)

def update_results(lists):
    with open(os.path.join(homepath,datadir+"previous_results.json"),'w') as f:
        json.dump(lists,f)

def init_previous_results():
    global deltaFields
    global AllMetricDict
    global firstresult
    getClusterInfo()
    getNodeInfo()
    getIndexInfo()
    firstResult = {}
    for metric in AllMetricDict.keys():
        if metric.split("[")[0] in deltaFields:
            firstResult[metric] = AllMetricDict[metric]
    update_results(firstResult)
    AllMetricDict = {}
    AllMetricList = []
    AllMetricList.append("timestamp")
    AllMetricDict["timestamp"] = timestamp
    time.sleep(1)
    firstresult = False

def get_previous_results():
    with open(os.path.join(homepath,datadir+"previous_results.json"),'r') as f:
        return json.load(f)

if(os.path.isfile(homepath+"/"+datadir+"previous_results.json") == False):
    firstresult = True
    init_previous_results()
previousResult = get_previous_results()
getClusterInfo()
getNodeInfo()
getIndexInfo()
writeToCsv()
update_results(newResult)
