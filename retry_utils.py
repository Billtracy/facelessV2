"""
Retry utilities for API calls with exponential backoff
"""
import time
import random
from typing import Callable, Any, Optional


def retry_with_backoff(
    func: Callable,
    max_retries: int = 3,
    initial_delay: float = 1.0,
    max_delay: float = 10.0,
    exponential_base: float = 2.0,
    jitter: bool = True,
    exceptions: tuple = (Exception,),
    logger: Optional[Any] = None
) -> Any:
    """
    Retry a function with exponential backoff.
    
    Args:
        func: Function to retry
        max_retries: Maximum number of retry attempts
        initial_delay: Initial delay in seconds
        max_delay: Maximum delay in seconds
        exponential_base: Base for exponential backoff
        jitter: Add random jitter to delay
        exceptions: Tuple of exceptions to catch and retry
        logger: Optional logger for tracking retries
    
    Returns:
        Result of func() if successful
    
    Raises:
        Last exception if all retries fail
    """
    delay = initial_delay
    
    for attempt in range(max_retries + 1):
        try:
            return func()
        except exceptions as e:
            if attempt == max_retries:
                if logger:
                    logger.error(f"Max retries ({max_retries}) reached. Last error: {e}")
                raise
            
            # Calculate delay with exponential backoff
            if jitter:
                # Add random jitter (0-100% of delay)
                actual_delay = delay * (0.5 + random.random() * 0.5)
            else:
                actual_delay = delay
            
            actual_delay = min(actual_delay, max_delay)
            
            if logger:
                logger.warning(f"Attempt {attempt + 1}/{max_retries} failed: {e}. Retrying in {actual_delay:.1f}s...")
            
            time.sleep(actual_delay)
            delay *= exponential_base
    
    # Should never reach here, but just in case
    raise Exception("Unexpected retry loop exit")
