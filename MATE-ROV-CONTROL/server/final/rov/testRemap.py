from hardware.controller import ControllerMapper
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("FriendlyTest")

def test_friendly_names():
    mapper = ControllerMapper()
    
    # Test using internal button names (should work)
    logger.info("=== Testing with internal button names ===")
    success = mapper.set_mapping('a', 'b')
    logger.info(f"Mapping 'a' -> 'b': {'Success' if success else 'Failed'}")
    
    # Test using friendly button names (should work with fix)
    logger.info("\n=== Testing with friendly button names ===")
    success = mapper.set_mapping('action 0', 'action 1')
    logger.info(f"Mapping 'action 0' -> 'action 1': {'Success' if success else 'Failed'}")
    
    # Check what actually got mapped
    logger.info(f"Current mapping for 'a': {mapper.mapping['a']}")
    
    # Save and reload to verify persistence
    mapper.save_mapping()
    new_mapper = ControllerMapper()
    logger.info(f"Reloaded mapping for 'a': {new_mapper.mapping['a']}")

if __name__ == "__main__":
    test_friendly_names()