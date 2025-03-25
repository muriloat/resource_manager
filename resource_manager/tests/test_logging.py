import logging
from client.config import ClientConfig
from client.services.service_controller import ServiceController

def test_metadata_logging():
    # Set up configuration with DEBUG logging
    config = ClientConfig()
    config.set_log_level("DEBUG")
    
    # Get the logger
    logger = config.logger
    logger.info("Starting metadata test")
    
    # Create a service controller
    host = config.get_host_config()
    controller = ServiceController(
        base_url=host["base_url"],
        timeout=host["timeout"],
        logger=logger
    )
    
    # List services
    try:
        services = controller.list_services()
        logger.info(f"Found {len(services)} services")
        
        # Test metadata for each service
        for service in services:
            logger.info(f"Testing metadata for {service}")
            metadata = controller.get_service_metadata(service)
            logger.info(f"Result: {metadata}")
    
    except Exception as e:
        logger.error(f"Test failed: {e}", exc_info=True)
    
    logger.info("Test completed")

if __name__ == "__main__":
    test_metadata_logging()