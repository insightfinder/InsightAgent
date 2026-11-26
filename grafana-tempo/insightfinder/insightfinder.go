package insightfinder

import (
	"context"
	"crypto/tls"
	"fmt"
	"time"

	config "github.com/insightfinder/grafana-tempo-agent/configs"
	coltracepb "go.opentelemetry.io/proto/otlp/collector/trace/v1"
	tracepb "go.opentelemetry.io/proto/otlp/trace/v1"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials"
	"google.golang.org/grpc/credentials/insecure"
	"google.golang.org/grpc/metadata"
)

const (
	maxExportMessageBytes = 64 << 20
	exportTimeout         = 30 * time.Second
)

type Service struct {
	config config.InsightFinderConfig
	conn   *grpc.ClientConn
	client coltracepb.TraceServiceClient
	header metadata.MD
}

func NewService(cfg config.InsightFinderConfig) (*Service, error) {
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
		return nil, fmt.Errorf("failed to connect trace server %s: %w", cfg.TraceServer, err)
	}
	return &Service{
		config: cfg,
		conn:   conn,
		client: coltracepb.NewTraceServiceClient(conn),
		header: metadata.Pairs(
			"ifuser", cfg.Username,
			"iflicensekey", cfg.LicenseKey,
			"ifproject", cfg.ProjectName,
			"ifsystem", cfg.SystemName,
		),
	}, nil
}

func (s *Service) SendTrace(ctx context.Context, traces *tracepb.TracesData) error {
	ctx = metadata.NewOutgoingContext(ctx, s.header)
	ctx, cancel := context.WithTimeout(ctx, exportTimeout)
	defer cancel()

	resp, err := s.client.Export(ctx, &coltracepb.ExportTraceServiceRequest{ResourceSpans: traces.ResourceSpans})
	if err != nil {
		return err
	}
	if partial := resp.GetPartialSuccess(); partial != nil && partial.GetRejectedSpans() > 0 {
		return fmt.Errorf("trace server rejected %d spans: %s", partial.GetRejectedSpans(), partial.GetErrorMessage())
	}
	return nil
}

func (s *Service) Close() error {
	return s.conn.Close()
}
