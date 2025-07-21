"""
Main FastAPI application for the Zabbix Webhook Agent
"""
import logging
import json
from datetime import datetime
from typing import Dict, Any, Optional

from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.core.config import settings, config_manager
from src.core.models import WebhookResponse, HealthResponse
from src.utils.auth import get_current_user
from src.processors.data_processor import DataProcessor
from src.clients.insightfinder_client import InsightFinderClient
from src.utils.utils import LoggerUtils, DataValidation, metrics_collector

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Zabbix Webhook Agent",
    description="HTTP server for processing Zabbix webhooks and forwarding to InsightFinder",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize clients
data_processor = DataProcessor()

# Function to get InsightFinder client for a specific config
def get_insightfinder_client(config_name: Optional[str] = None) -> InsightFinderClient:
    """Get InsightFinder client with specific configuration"""
    return InsightFinderClient(config_name=config_name)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler"""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "status": "error",
            "message": "Internal server error",
            "timestamp": datetime.now().isoformat()
        }
    )


@app.get("/")
async def root():
    """Root endpoint with API information"""
    return {
        "name": "Zabbix Webhook Agent",
        "version": "1.0.0",
        "description": "HTTP server for processing Zabbix webhooks and forwarding to InsightFinder",
        "status": "running"
    }


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint"""
    # Validate legacy configuration
    legacy_config_valid = DataValidation.validate_insightfinder_config()
    
    # Validate multi-project configurations
    config_count = len(config_manager.list_configs())
    configs_valid = config_count > 0
    
    # Overall status
    overall_status = "healthy"
    if not legacy_config_valid and not configs_valid:
        overall_status = "configuration_error"
    elif not configs_valid:
        overall_status = "partial_configuration"
    
    return HealthResponse(
        status=overall_status,
        timestamp=datetime.now(),
        version="1.0.0"
    )


@app.post("/webhook/zabbix", response_model=WebhookResponse)
async def receive_zabbix_webhook(
    request: Request,
    current_user: dict = Depends(get_current_user),
    config_name: Optional[str] = None
):
    """
    Receive and process Zabbix webhook data
    
    Args:
        request: FastAPI request object
        current_user: Authenticated user information
        config_name: Name of the InsightFinder configuration to use
        
    Returns:
        WebhookResponse: Processing status and details
    """
    try:
        # Get raw data from request
        raw_data = await request.json()
        
        # Check if config_name is provided in the request body
        if 'config_name' in raw_data:
            config_name = raw_data.pop('config_name')
        
        # Increment metrics
        metrics_collector.increment_webhook_received()
        
        logger.info(f"Received Zabbix webhook from authenticated user using config: {config_name or 'default'}")
        LoggerUtils.log_webhook_data(raw_data, "Zabbix")
        
        # Sanitize and process the webhook data
        alert_data = data_processor.process_zabbix_webhook(raw_data=raw_data)

        # Validate the processed data
        if not data_processor.validate_required_fields(alert_data):
            raise HTTPException(
                status_code=400,
                detail="Invalid webhook data: missing required fields"
            )
        
        # Enrich the data
        enriched_data = data_processor.enrich_alert_data(alert_data)
        
        # Increment processed counter
        metrics_collector.increment_webhook_processed()
        
        # Get InsightFinder client for the specified config
        insightfinder_client = get_insightfinder_client(config_name)
        
        # Send to InsightFinder
        data_sent = False
        try:
            metric_success = insightfinder_client.send_metric_data(enriched_data)
            log_success = insightfinder_client.send_log_data(enriched_data)
            
            data_sent = metric_success or log_success
            
            if data_sent:
                metrics_collector.increment_data_sent()
                logger.info("Successfully forwarded data to InsightFinder")
            else:
                metrics_collector.increment_errors()
                logger.warning("Failed to forward data to InsightFinder")
                
        except Exception as e:
            metrics_collector.increment_errors()
            logger.error(f"Error forwarding to InsightFinder: {e}")
        
        # Return response
        return WebhookResponse(
            status="success" if data_sent else "partial_success",
            message=f"Webhook processed successfully. Data sent to InsightFinder: {data_sent}",
            processed_at=datetime.now(),
            data_sent=data_sent
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing webhook: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Error processing webhook: {str(e)}"
        )


@app.post("/webhook/test")
async def test_webhook(
    data: Dict[str, Any],
    current_user: dict = Depends(get_current_user)
):
    """
    Test endpoint for webhook functionality (without forwarding to InsightFinder)
    
    Args:
        data: Test webhook data
        current_user: Authenticated user information
        
    Returns:
        Dict: Processed data for testing
    """
    try:
        logger.info("Processing test webhook")
        
        # Process the data
        alert_data = data_processor.process_zabbix_webhook(data)
        enriched_data = data_processor.enrich_alert_data(alert_data)
        
        return {
            "status": "success",
            "message": "Test webhook processed successfully",
            "processed_data": enriched_data,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error in test webhook: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error processing test webhook: {str(e)}"
        )


@app.get("/status")
async def get_status(current_user: dict = Depends(get_current_user)):
    """
    Get server status and configuration (authenticated endpoint)
    
    Args:
        current_user: Authenticated user information
        
    Returns:
        Dict: Server status information
    """
    # Get legacy configuration status
    legacy_config = {
        "base_url": settings.insightfinder_base_url,
        "project_name": settings.insightfinder_project_name,
        "username": settings.insightfinder_username,
        "configured": bool(settings.insightfinder_license_key)
    }
    
    # Get multi-project configurations
    available_configs = config_manager.get_config_summary()
    
    return {
        "server_status": "running",
        "metrics": metrics_collector.get_stats(),
        "legacy_insightfinder_config": legacy_config,
        "available_configurations": available_configs,
        "default_config": config_manager.default_config_name,
        "authentication": {
            "method": "api_key",
            "user": current_user
        },
        "timestamp": datetime.now().isoformat()
    }


@app.get("/configs")
async def list_configurations(current_user: dict = Depends(get_current_user)):
    """
    List all available InsightFinder configurations
    
    Args:
        current_user: Authenticated user information
        
    Returns:
        Dict: Available configurations with details
    """
    try:
        configurations = config_manager.get_config_summary()
        available_configs = config_manager.list_configs()
        
        return {
            "status": "success",
            "default_config": config_manager.default_config_name,
            "available_configs": available_configs,
            "configurations": configurations,
            "total_configs": len(configurations),
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error listing configurations: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error listing configurations: {str(e)}"
        )


@app.get("/configs/{config_name}")
async def get_configuration_details(
    config_name: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Get details for a specific configuration
    
    Args:
        config_name: Name of the configuration
        current_user: Authenticated user information
        
    Returns:
        Dict: Configuration details
    """
    try:
        if not config_manager.has_config(config_name):
            raise HTTPException(
                status_code=404,
                detail=f"Configuration '{config_name}' not found"
            )
        
        config = config_manager.get_config(config_name)
        config_dict = config.to_dict()
        
        # Remove sensitive information
        safe_config = config_dict.copy()
        safe_config['password'] = "***" if config_dict['password'] else ""
        safe_config['license_key'] = "***" if config_dict['license_key'] else ""
        
        return {
            "status": "success",
            "config_name": config_name,
            "configuration": safe_config,
            "timestamp": datetime.now().isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting configuration {config_name}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error getting configuration: {str(e)}"
        )


@app.post("/configs/reload")
async def reload_configurations(current_user: dict = Depends(get_current_user)):
    """
    Reload all configurations from disk
    
    Args:
        current_user: Authenticated user information
        
    Returns:
        Dict: Reload status
    """
    try:
        config_manager.reload_configs()
        configurations = config_manager.get_config_summary()
        
        return {
            "status": "success",
            "message": "Configurations reloaded successfully",
            "configurations": configurations,
            "total_configs": len(configurations),
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error reloading configurations: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error reloading configurations: {str(e)}"
        )


@app.post("/webhook/zabbix/{config_name}", response_model=WebhookResponse)
async def receive_zabbix_webhook_with_config(
    config_name: str,
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    """
    Receive and process Zabbix webhook data with specific configuration
    
    Args:
        config_name: Name of the InsightFinder configuration to use
        request: FastAPI request object
        current_user: Authenticated user information
        
    Returns:
        WebhookResponse: Processing status and details
    """
    # Validate configuration exists
    if not config_manager.has_config(config_name):
        raise HTTPException(
            status_code=404,
            detail=f"Configuration '{config_name}' not found. Available: {config_manager.list_configs()}"
        )
    
    try:
        # Get raw data from request
        raw_data = await request.json()
        
        # Increment metrics
        metrics_collector.increment_webhook_received()
        
        logger.info(f"Received Zabbix webhook from authenticated user using config: {config_name}")
        LoggerUtils.log_webhook_data(raw_data, "Zabbix")
        
        # Sanitize and process the webhook data
        alert_data = data_processor.process_zabbix_webhook(raw_data=raw_data)
        
        # Validate the processed data
        if not data_processor.validate_required_fields(alert_data):
            raise HTTPException(
                status_code=400,
                detail="Invalid webhook data: missing required fields"
            )
        
        # Enrich the data
        enriched_data = data_processor.enrich_alert_data(alert_data)
        
        # Increment processed counter
        metrics_collector.increment_webhook_processed()
        
        # Get InsightFinder client for the specified config
        insightfinder_client = get_insightfinder_client(config_name)
        
        # Send to InsightFinder
        data_sent = False
        try:
            metric_success = insightfinder_client.send_metric_data(enriched_data)
            log_success = insightfinder_client.send_log_data(enriched_data)
            
            data_sent = metric_success or log_success
            
            if data_sent:
                metrics_collector.increment_data_sent()
                logger.info(f"Successfully forwarded data to InsightFinder using config: {config_name}")
            else:
                metrics_collector.increment_errors()
                logger.warning(f"Failed to forward data to InsightFinder using config: {config_name}")
                
        except Exception as e:
            metrics_collector.increment_errors()
            logger.error(f"Error forwarding to InsightFinder: {e}")
        
        # Return response
        return WebhookResponse(
            status="success" if data_sent else "partial_success",
            message=f"Webhook processed successfully using config '{config_name}'. Data sent to InsightFinder: {data_sent}",
            processed_at=datetime.now(),
            data_sent=data_sent
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing webhook: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Error processing webhook: {str(e)}"
        )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=80,
        reload=True,
        log_level=settings.log_level.lower()
    )
