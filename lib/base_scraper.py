from urllib.parse import urlparse, parse_qs
from logging import Logger
import time
import os
from tenacity import (
    retry,
    stop_after_attempt,
    wait_fixed,
    retry_if_exception_type,
    wait_exponential,
)
import uuid
import re
from datetime import datetime
import requests
from bs4 import BeautifulSoup


class BaseScraper(object):
    session: requests.Session
    logger: Logger
    
    @retry(
        reraise=True,
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type(requests.exceptions.ChunkedEncodingError)
    )
    
    def fetch_document_content(self, url):
        
        try:
            response = self.session.request(
                method="GET", url=url, timeout=(10, 30)
            )
            response_size_kb = round(len(response.content)/1024) 
            elapsed_time_seconds = round(response.elapsed.total_seconds(), 2)
            self.logger.info(
                f"GET [{response.status_code}]: {url} {elapsed_time_seconds} {response_size_kb}"
            )
            response.raise_for_status()
            content = response.content
            
        except requests.exceptions.ChunkedEncodingError as e:
            self.logger.error(f"ChunkedEncodingError occurred: {e}")
            raise
        except (requests.exceptions.Timeout, requests.exceptions.ReadTimeout) as e:
            self.logger.error(f"Timeout occurred: {e}")
            content = bytes(f"Timeout @ {url}".encode("utf-8"))
        except requests.HTTPError as e:
            self.logger.error(e)
            content = bytes(f"{e} @ {url}".encode("utf-8"))

        return content