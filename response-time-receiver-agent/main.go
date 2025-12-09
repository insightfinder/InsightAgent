package main

import (
	"flag"
	"fmt"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/gofiber/fiber/v2"
	"github.com/gofiber/fiber/v2/middleware/cors"
	"github.com/gofiber/fiber/v2/middleware/logger"
	"github.com/gofiber/fiber/v2/middleware/recover"
	"github.com/insightfinder/receiver-agent/configs"
	"github.com/insightfinder/receiver-agent/receiver"
	"github.com/insightfinder/receiver-agent/sampler"
	"github.com/sirupsen/logrus"
)

var (
	configPath = flag.String("config", "configs/config.yaml", "Path to configuration file")
)

func main() {
	flag.Parse()

	// Initialize logger
	initLogger()

	logrus.Info("=== InsightFinder Receiver Agent ===")
	logrus.Infof("Starting receiver agent...")

	// Load configuration
	config, err := configs.LoadConfig(*configPath)
	if err != nil {
		logrus.Fatalf("Failed to load configuration: %v", err)
	}

	// Set log level from config
	setLogLevel(config.Agent.LogLevel)

	// Create Fiber app
	app := fiber.New(fiber.Config{
		AppName:      "InsightFinder Receiver Agent",
		ServerHeader: "Receiver-Agent",
		ErrorHandler: customErrorHandler,
		ReadTimeout:  30 * time.Second,
		WriteTimeout: 30 * time.Second,
		IdleTimeout:  120 * time.Second,
	})

	// Add middleware
	app.Use(recover.New(recover.Config{
		EnableStackTrace: true,
	}))

	app.Use(logger.New(logger.Config{
		Format:     "[${time}] ${status} - ${method} ${path} (${latency})\n",
		TimeFormat: "2006-01-02 15:04:05",
		TimeZone:   "UTC",
	}))

	app.Use(cors.New(cors.Config{
		AllowOrigins: "*",
		AllowMethods: "GET,POST,PUT,DELETE,OPTIONS",
		AllowHeaders: "Origin, Content-Type, Accept, Authorization",
	}))

	// Setup routes
	receiver.SetupRoutes(app, config)

	// Initialize and start sampler if enabled
	samplerService := sampler.NewSamplerService(&config.Sampler, config)
	samplerService.Start()

	// Start server in a goroutine
	serverAddr := fmt.Sprintf(":%d", config.Agent.ServerPort)
	go func() {
		logrus.Infof("Starting HTTP server on %s", serverAddr)
		if err := app.Listen(serverAddr); err != nil {
			logrus.Fatalf("Failed to start server: %v", err)
		}
	}()

	logrus.Infof("Receiver agent started successfully on port %d", config.Agent.ServerPort)
	logrus.Info("Press Ctrl+C to stop...")

	// Wait for interrupt signal
	quit := make(chan os.Signal, 1)
	signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)
	<-quit

	logrus.Info("Shutting down receiver agent...")

	// Stop sampler service
	samplerService.Stop()

	// Graceful shutdown
	if err := app.Shutdown(); err != nil {
		logrus.Errorf("Error during shutdown: %v", err)
	}

	logrus.Info("Receiver agent stopped")
}

// initLogger initializes the logger
func initLogger() {
	logrus.SetFormatter(&logrus.TextFormatter{
		FullTimestamp:   true,
		TimestampFormat: "2006-01-02 15:04:05",
	})
	logrus.SetOutput(os.Stdout)
	logrus.SetLevel(logrus.InfoLevel)
}

// setLogLevel sets the log level based on configuration
func setLogLevel(level string) {
	switch level {
	case "DEBUG":
		logrus.SetLevel(logrus.DebugLevel)
	case "INFO":
		logrus.SetLevel(logrus.InfoLevel)
	case "WARN", "WARNING":
		logrus.SetLevel(logrus.WarnLevel)
	case "ERROR":
		logrus.SetLevel(logrus.ErrorLevel)
	default:
		logrus.SetLevel(logrus.InfoLevel)
		logrus.Warnf("Unknown log level '%s', defaulting to INFO", level)
	}
	logrus.Infof("Log level set to: %s", logrus.GetLevel().String())
}

// customErrorHandler handles Fiber errors
func customErrorHandler(c *fiber.Ctx, err error) error {
	code := fiber.StatusInternalServerError

	if e, ok := err.(*fiber.Error); ok {
		code = e.Code
	}

	logrus.Errorf("HTTP Error: %d - %v", code, err)

	return c.Status(code).JSON(receiver.APIResponse{
		Success: false,
		Message: err.Error(),
	})
}
