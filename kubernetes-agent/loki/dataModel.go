package loki

import "time"

type LokiLogData struct {
	Namespace string    `validate:"required"`
	Timestamp time.Time `validate:"required"`
	Pod       string    `validate:"required"`
	Text      string    `validate:"required"`
}

type LogQueryResponseBody struct {
	Status string `json:"status"`
	Data   struct {
		ResultType string `json:"resultType"`
		Result     []struct {
			Stream struct {
				App       string `json:"app"`
				Container string `json:"container"`
				Filename  string `json:"filename"`
				Instance  string `json:"instance"`
				Job       string `json:"job"`
				Namespace string `json:"namespace"`
				NodeName  string `json:"node_name"`
				Pod       string `json:"pod"`
				Stream    string `json:"stream"`
			} `json:"stream"`
			Values [][]string `json:"values"`
		} `json:"result"`
		Stats struct {
			Summary struct {
				BytesProcessedPerSecond int     `json:"bytesProcessedPerSecond"`
				LinesProcessedPerSecond int     `json:"linesProcessedPerSecond"`
				TotalBytesProcessed     int     `json:"totalBytesProcessed"`
				TotalLinesProcessed     int     `json:"totalLinesProcessed"`
				ExecTime                float64 `json:"execTime"`
				QueueTime               float64 `json:"queueTime"`
				Subqueries              int     `json:"subqueries"`
				TotalEntriesReturned    int     `json:"totalEntriesReturned"`
				Splits                  int     `json:"splits"`
				Shards                  int     `json:"shards"`
			} `json:"summary"`
			Querier struct {
				Store struct {
					TotalChunksRef        int `json:"totalChunksRef"`
					TotalChunksDownloaded int `json:"totalChunksDownloaded"`
					ChunksDownloadTime    int `json:"chunksDownloadTime"`
					Chunk                 struct {
						HeadChunkBytes    int `json:"headChunkBytes"`
						HeadChunkLines    int `json:"headChunkLines"`
						DecompressedBytes int `json:"decompressedBytes"`
						DecompressedLines int `json:"decompressedLines"`
						CompressedBytes   int `json:"compressedBytes"`
						TotalDuplicates   int `json:"totalDuplicates"`
					} `json:"chunk"`
				} `json:"store"`
			} `json:"querier"`
			Ingester struct {
				TotalReached       int `json:"totalReached"`
				TotalChunksMatched int `json:"totalChunksMatched"`
				TotalBatches       int `json:"totalBatches"`
				TotalLinesSent     int `json:"totalLinesSent"`
				Store              struct {
					TotalChunksRef        int `json:"totalChunksRef"`
					TotalChunksDownloaded int `json:"totalChunksDownloaded"`
					ChunksDownloadTime    int `json:"chunksDownloadTime"`
					Chunk                 struct {
						HeadChunkBytes    int `json:"headChunkBytes"`
						HeadChunkLines    int `json:"headChunkLines"`
						DecompressedBytes int `json:"decompressedBytes"`
						DecompressedLines int `json:"decompressedLines"`
						CompressedBytes   int `json:"compressedBytes"`
						TotalDuplicates   int `json:"totalDuplicates"`
					} `json:"chunk"`
				} `json:"store"`
			} `json:"ingester"`
			Cache struct {
				Chunk struct {
					EntriesFound     int `json:"entriesFound"`
					EntriesRequested int `json:"entriesRequested"`
					EntriesStored    int `json:"entriesStored"`
					BytesReceived    int `json:"bytesReceived"`
					BytesSent        int `json:"bytesSent"`
					Requests         int `json:"requests"`
					DownloadTime     int `json:"downloadTime"`
				} `json:"chunk"`
				Index struct {
					EntriesFound     int `json:"entriesFound"`
					EntriesRequested int `json:"entriesRequested"`
					EntriesStored    int `json:"entriesStored"`
					BytesReceived    int `json:"bytesReceived"`
					BytesSent        int `json:"bytesSent"`
					Requests         int `json:"requests"`
					DownloadTime     int `json:"downloadTime"`
				} `json:"index"`
				Result struct {
					EntriesFound     int `json:"entriesFound"`
					EntriesRequested int `json:"entriesRequested"`
					EntriesStored    int `json:"entriesStored"`
					BytesReceived    int `json:"bytesReceived"`
					BytesSent        int `json:"bytesSent"`
					Requests         int `json:"requests"`
					DownloadTime     int `json:"downloadTime"`
				} `json:"result"`
			} `json:"cache"`
		} `json:"stats"`
	} `json:"data"`
}
