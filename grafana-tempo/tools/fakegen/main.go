package main

import (
	"bytes"
	"context"
	"crypto/rand"
	"flag"
	"fmt"
	"io"
	"log/slog"
	mrand "math/rand/v2"
	"net/http"
	"os"
	"os/signal"
	"time"

	coltracepb "go.opentelemetry.io/proto/otlp/collector/trace/v1"
	commonpb "go.opentelemetry.io/proto/otlp/common/v1"
	resourcepb "go.opentelemetry.io/proto/otlp/resource/v1"
	tracepb "go.opentelemetry.io/proto/otlp/trace/v1"
	"google.golang.org/protobuf/proto"
)

type service struct {
	name string
	host string
}

var (
	frontend  = service{"frontend", "web-01"}
	checkout  = service{"checkout-service", "app-01"}
	payment   = service{"payment-service", "app-02"}
	inventory = service{"inventory-service", "app-03"}
	database  = service{"orders-db", "db-01"}
)

type spanBuilder struct {
	traceID []byte
	spans   map[service][]*tracepb.Span
}

func main() {
	endpoint := flag.String("endpoint", "http://localhost:4318", "Tempo OTLP HTTP endpoint")
	perTick := flag.Int("n", 5, "traces per tick")
	tick := flag.Duration("interval", 10*time.Second, "time between ticks")
	ticks := flag.Int("ticks", 0, "number of ticks, 0 runs until interrupted")
	errorRate := flag.Float64("error-rate", 0.1, "fraction of traces with a failed payment")
	slowRate := flag.Float64("slow-rate", 0.1, "fraction of traces with a slow database query")
	flag.Parse()

	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt)
	defer stop()

	client := &http.Client{Timeout: 10 * time.Second}
	for i := 0; *ticks == 0 || i < *ticks; i++ {
		req := &coltracepb.ExportTraceServiceRequest{}
		ids := []string{}
		for j := 0; j < *perTick; j++ {
			fail := mrand.Float64() < *errorRate
			slow := mrand.Float64() < *slowRate
			b := buildTrace(time.Now().Add(-time.Duration(mrand.IntN(5000))*time.Millisecond), fail, slow)
			req.ResourceSpans = append(req.ResourceSpans, b.resourceSpans()...)
			ids = append(ids, fmt.Sprintf("%x", b.traceID))
		}
		if err := send(ctx, client, *endpoint, req); err != nil {
			slog.Error("send", "error", err)
		} else {
			slog.Info("sent traces", "count", len(ids), "first_trace_id", ids[0])
		}
		if *ticks != 0 && i == *ticks-1 {
			break
		}
		select {
		case <-ctx.Done():
			return
		case <-time.After(*tick):
		}
	}
}

func buildTrace(start time.Time, fail, slow bool) *spanBuilder {
	b := &spanBuilder{traceID: randomBytes(16), spans: map[service][]*tracepb.Span{}}

	dbLatency := time.Duration(5+mrand.IntN(20)) * time.Millisecond
	if slow {
		dbLatency = time.Duration(1500+mrand.IntN(1500)) * time.Millisecond
	}
	payLatency := time.Duration(40+mrand.IntN(60)) * time.Millisecond
	invLatency := time.Duration(10+mrand.IntN(20)) * time.Millisecond

	checkoutLatency := invLatency + dbLatency + payLatency + 15*time.Millisecond
	totalLatency := checkoutLatency + 20*time.Millisecond

	root := b.add(frontend, nil, "GET /api/checkout", tracepb.Span_SPAN_KIND_SERVER, start, totalLatency,
		attrs("http.request.method", "GET", "url.path", "/api/checkout", "http.response.status_code", statusCode(fail)))
	callCheckout := b.add(frontend, root, "POST checkout-service/PlaceOrder", tracepb.Span_SPAN_KIND_CLIENT, start.Add(5*time.Millisecond), checkoutLatency,
		attrs("rpc.system", "grpc", "rpc.service", "CheckoutService", "rpc.method", "PlaceOrder"))
	placeOrder := b.add(checkout, callCheckout, "CheckoutService/PlaceOrder", tracepb.Span_SPAN_KIND_SERVER, start.Add(6*time.Millisecond), checkoutLatency-2*time.Millisecond,
		attrs("rpc.system", "grpc", "rpc.service", "CheckoutService", "rpc.method", "PlaceOrder", "app.order.items", fmt.Sprint(1+mrand.IntN(5))))

	t := start.Add(8 * time.Millisecond)
	reserve := b.add(checkout, placeOrder, "InventoryService/Reserve", tracepb.Span_SPAN_KIND_CLIENT, t, invLatency,
		attrs("rpc.system", "grpc", "rpc.service", "InventoryService", "rpc.method", "Reserve"))
	b.add(inventory, reserve, "InventoryService/Reserve", tracepb.Span_SPAN_KIND_SERVER, t.Add(time.Millisecond), invLatency-2*time.Millisecond,
		attrs("rpc.system", "grpc", "app.sku.count", fmt.Sprint(1+mrand.IntN(5))))

	t = t.Add(invLatency + time.Millisecond)
	query := b.add(checkout, placeOrder, "INSERT orders", tracepb.Span_SPAN_KIND_CLIENT, t, dbLatency,
		attrs("db.system", "postgresql", "db.operation.name", "INSERT", "db.collection.name", "orders"))
	b.add(database, query, "INSERT orders", tracepb.Span_SPAN_KIND_SERVER, t.Add(time.Millisecond), dbLatency-time.Millisecond,
		attrs("db.system", "postgresql", "db.query.text", "INSERT INTO orders (id, user_id, total) VALUES ($1, $2, $3)"))

	t = t.Add(dbLatency + time.Millisecond)
	charge := b.add(checkout, placeOrder, "PaymentService/Charge", tracepb.Span_SPAN_KIND_CLIENT, t, payLatency,
		attrs("rpc.system", "grpc", "rpc.service", "PaymentService", "rpc.method", "Charge"))
	paySpan := b.add(payment, charge, "PaymentService/Charge", tracepb.Span_SPAN_KIND_SERVER, t.Add(time.Millisecond), payLatency-2*time.Millisecond,
		attrs("rpc.system", "grpc", "app.payment.amount", fmt.Sprintf("%.2f", 10+mrand.Float64()*490), "app.payment.card_type", "visa"))

	if fail {
		msg := "card declined: insufficient funds"
		for _, s := range []*tracepb.Span{paySpan, charge, placeOrder, callCheckout, root} {
			s.Status = &tracepb.Status{Code: tracepb.Status_STATUS_CODE_ERROR, Message: msg}
		}
		paySpan.Events = append(paySpan.Events, &tracepb.Span_Event{
			TimeUnixNano: paySpan.EndTimeUnixNano - uint64(time.Millisecond),
			Name:         "exception",
			Attributes:   attrs("exception.type", "PaymentDeclinedError", "exception.message", msg),
		})
	}
	return b
}

func (b *spanBuilder) add(svc service, parent *tracepb.Span, name string, kind tracepb.Span_SpanKind, start time.Time, d time.Duration, a []*commonpb.KeyValue) *tracepb.Span {
	s := &tracepb.Span{
		TraceId:           b.traceID,
		SpanId:            randomBytes(8),
		Name:              name,
		Kind:              kind,
		StartTimeUnixNano: uint64(start.UnixNano()),
		EndTimeUnixNano:   uint64(start.Add(d).UnixNano()),
		Attributes:        a,
		Status:            &tracepb.Status{Code: tracepb.Status_STATUS_CODE_OK},
	}
	if parent != nil {
		s.ParentSpanId = parent.SpanId
	}
	b.spans[svc] = append(b.spans[svc], s)
	return s
}

func (b *spanBuilder) resourceSpans() []*tracepb.ResourceSpans {
	out := []*tracepb.ResourceSpans{}
	for _, svc := range []service{frontend, checkout, inventory, database, payment} {
		spans := b.spans[svc]
		if len(spans) == 0 {
			continue
		}
		out = append(out, &tracepb.ResourceSpans{
			Resource: &resourcepb.Resource{Attributes: attrs(
				"service.name", svc.name,
				"host.name", svc.host,
				"deployment.environment.name", "tempo-demo",
			)},
			ScopeSpans: []*tracepb.ScopeSpans{{
				Scope: &commonpb.InstrumentationScope{Name: "insightfinder-tempo-fakegen"},
				Spans: spans,
			}},
		})
	}
	return out
}

func send(ctx context.Context, client *http.Client, endpoint string, req *coltracepb.ExportTraceServiceRequest) error {
	body, err := proto.Marshal(req)
	if err != nil {
		return err
	}
	httpReq, err := http.NewRequestWithContext(ctx, http.MethodPost, endpoint+"/v1/traces", bytes.NewReader(body))
	if err != nil {
		return err
	}
	httpReq.Header.Set("Content-Type", "application/x-protobuf")
	resp, err := client.Do(httpReq)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode/100 != 2 {
		msg, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("tempo returned %d: %s", resp.StatusCode, msg)
	}
	return nil
}

func attrs(kv ...string) []*commonpb.KeyValue {
	out := make([]*commonpb.KeyValue, 0, len(kv)/2)
	for i := 0; i+1 < len(kv); i += 2 {
		out = append(out, &commonpb.KeyValue{
			Key:   kv[i],
			Value: &commonpb.AnyValue{Value: &commonpb.AnyValue_StringValue{StringValue: kv[i+1]}},
		})
	}
	return out
}

func statusCode(fail bool) string {
	if fail {
		return "500"
	}
	return "200"
}

func randomBytes(n int) []byte {
	b := make([]byte, n)
	if _, err := rand.Read(b); err != nil {
		panic(err)
	}
	return b
}
