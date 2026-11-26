package main

import (
	"context"
	"crypto/tls"
	"fmt"
	"time"

	coltracepb "go.opentelemetry.io/proto/otlp/collector/trace/v1"
	tracepb "go.opentelemetry.io/proto/otlp/trace/v1"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials"
	"google.golang.org/grpc/credentials/insecure"
	"google.golang.org/grpc/metadata"
)

const maxExportMessageBytes = 64 << 20

type TraceSender struct {
	cfg    InsightFinderConfig
	conn   *grpc.ClientConn
	client coltracepb.TraceServiceClient
	md     metadata.MD
}

func NewTraceSender(cfg InsightFinderConfig) (*TraceSender, error) {
	var creds credentials.TransportCredentials
	if cfg.TLS {
		creds = credentials.NewTLS(&tls.Config{InsecureSkipVerify: cfg.InsecureSkipVerify})
	} else {
		creds = insecure.NewCredentials()
	}
	conn, err := grpc.NewClient(cfg.TraceServer,
		grpc.WithTransportCredentials(creds),
		grpc.WithDefaultCallOptions(grpc.MaxCallSendMsgSize(maxExportMessageBytes)),
	)
	if err != nil {
		return nil, fmt.Errorf("connect trace server %s: %w", cfg.TraceServer, err)
	}
	return &TraceSender{
		cfg:    cfg,
		conn:   conn,
		client: coltracepb.NewTraceServiceClient(conn),
		md: metadata.Pairs(
			"ifuser", cfg.Username,
			"iflicensekey", cfg.LicenseKey,
			"ifproject", cfg.ProjectName,
			"ifsystem", cfg.SystemName,
		),
	}, nil
}

func (s *TraceSender) Send(ctx context.Context, td *tracepb.TracesData) error {
	ctx = metadata.NewOutgoingContext(ctx, s.md)
	ctx, cancel := context.WithTimeout(ctx, 30*time.Second)
	defer cancel()
	resp, err := s.client.Export(ctx, &coltracepb.ExportTraceServiceRequest{ResourceSpans: td.ResourceSpans})
	if err != nil {
		return err
	}
	if ps := resp.GetPartialSuccess(); ps != nil && ps.GetRejectedSpans() > 0 {
		return fmt.Errorf("trace server rejected %d spans: %s", ps.GetRejectedSpans(), ps.GetErrorMessage())
	}
	return nil
}

func (s *TraceSender) Close() error {
	return s.conn.Close()
}
