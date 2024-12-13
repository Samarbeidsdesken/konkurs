

#from base_scraper import BaseScraper
from logging import Logger, getLogger
from selenium.webdriver.chrome.options import Options
from selenium import webdriver
from datetime import datetime, timedelta
from bs4 import BeautifulSoup as bs
import pandas as pd
import re
import requests
from tenacity import (
    retry,
    stop_after_attempt,
    wait_fixed,
    retry_if_exception_type,
    wait_exponential,
)

class AnnouncementsScraper():
    """
    A Class for scraping the content of: 
    https://w2.brreg.no/kunngjoring/kombisok.jsp?datoFra={from_date}&datoTil={to_date}&id_region=0&id_niva1=51&id_niva2=-+-+-&id_bransje1=0
    
    Args:
        from_date: The start of the periode the scraper collects announcements
        to_date: The end of the period the scraper collects announcements
        logger: Module level logging using logging.getLogger()
    """
    def __init__(self, from_date: str, to_date: str, logger: Logger):
        self.from_date = from_date
        self.to_date = to_date
        self.logger = logger
        self.url = f'https://w2.brreg.no/kunngjoring/kombisok.jsp?datoFra={from_date}&datoTil={to_date}&id_region=0&id_niva1=51&id_niva2=-+-+-&id_bransje1=0'
        self.session = requests.Session()
        self.page_source = None
        self.df = None
        
        # Convert string inputs to datetime objects

        # Check if to_date is less than from_date
        if datetime.strptime(self.to_date, '%d.%m.%Y') < datetime.strptime(from_date, '%d.%m.%Y'):
            raise ValueError(f"to_date ({self.to_date}) cannot be earlier than from_date ({self.from_date})")

        
    @retry(
        reraise=True,
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type(requests.exceptions.ChunkedEncodingError)
    )
    def fetch_document_content(self):
        """
        Uses bs4.BeautifulSoup to collect the response.content of url the instance.
        
        Args:
            None
        Returns:
            str: returns response.content
        Raises: 
            Timeout and HTTPError. ChunkedEncodingError after five attempts (@retry). 
        
        Example:
            from_date = datetime.strftime(datetime.now() - timedelta(1), format='%d.%m.%Y')
            to_date = datetime.strftime(datetime.now() - timedelta(1), format='%d.%m.%Y')
            
            job = AnnouncementsScraper(
                from_date = from_date,
                to_date = to_date,
                logger = getLogger(__name__)
                )
            
            job.fetch_document_content()
        """
        try:
            
            response = self.session.request(
                method="GET", url=self.url, timeout=(10, 30)
            )
            response_size_kb = round(len(response.content)/1024) 
            elapsed_time_seconds = round(response.elapsed.total_seconds(), 2)
            self.logger.info(
                f"GET [{response.status_code}]: {self.url} {elapsed_time_seconds} {response_size_kb}"
            )
            response.raise_for_status()
            content = response.content
            
        except requests.exceptions.ChunkedEncodingError as e:
            self.logger.error(f"ChunkedEncodingError occurred: {e}")
            raise
        except (requests.exceptions.Timeout, requests.exceptions.ReadTimeout) as e:
            self.logger.error(f"Timeout occurred: {e}")
            content = bytes(f"Timeout @ {self.url}".encode("utf-8"))
        except requests.HTTPError as e:
            self.logger.error(e)
            content = bytes(f"{e} @ {self.url}".encode("utf-8"))

        self.page_source = content
        
    def scrape(self):
        self.logger.warning('Note that AnnouncementsScraper.scrape(self) is depreciated.')
        options = Options()
        options.add_argument('--headless')
        
        url = f'https://w2.brreg.no/kunngjoring/kombisok.jsp?datoFra={self.from_date}&datoTil={self.to_date}&id_region=0&id_niva1=51&id_niva2=-+-+-&id_bransje1=0'
        
        driver = webdriver.Chrome(options=options)
        driver.get(url)
        
        self.page_source = driver.page_source.replace('\n', '')
    
    def source_to_df(self):
        """
        A method that parses self.page_source if it is provided.
        
        This method uses the class attribute `self.page_source` for parsing. If `self.page_source`
        is `None`, a ValueError will be raised.

        Raises: 
            ValueError: If self.page_source is None
            Exceptions: If it fails to parse the content, cannot find the table rows, or if it fails to parse data into a data frame.
            
        Returns:
            pd.dataframe
            
        Example:
            from_date = datetime.strftime(datetime.now() - timedelta(1), format='%d.%m.%Y')
            to_date = datetime.strftime(datetime.now() - timedelta(1), format='%d.%m.%Y')
            
            job = AnnouncementsScraper(
                from_date = from_date,
                to_date = to_date,
                logger = getLogger(__name__)
                )
            
            job.fetch_document_content()
            job.source_to_df()

        """
        try:
            if not self.page_source:
                self.logger.error(f'self.page_source is not collect from {self.url}')
                raise ValueError(f'self.page_source is not collect from {self.url}')
            
            soup = bs(self.page_source, 'html.parser')
        
        except Exception as ex:
            self.logger.error(f'Failed to parse page source content. \nError: {ex} \nURL: {self.url}')
            return None
        
        try:
            table_rows = soup.find_all('tr')
            
            if not table_rows:
                raise ValueError(f'Table rows not found at {self.url}')
        except Exception as e:
            self.logger.error(f'Error locating table rows: \nError: {ex} \nURL: {self.url}')
            return None
        
        try:
            df = pd.DataFrame()
            data = []
            # Loop through each table row  on the whole page
            for row in table_rows:
                row_data = []

                # ignore trs that has nested tables. These function as duplicates.
                if row.find('table'):
                    pass
                else:

                    # Check if any td in the row has a img-tag with an onclick function of kopier_orgnr.
                    has_td_img = [True if td.find(
                        'img', onclick=lambda x: x and 'kopier_orgnr' in x) else False for td in row.find_all('td')]

                    # If the img-tag is found, collect the data from the row.
                    if any(has_td_img):
                        
                        # Loop through each td in the row
                        for td in row.find_all('td'):

                            row_dict = {'navn': None, 'orgnr': None,
                                        'dato': None, 'type': None, 'url': None}

                            ## Look for img tags with the onclick function 'kopier_orgnr'
                            #img_tag = td.find(
                            #    'img', onclick=lambda x: x and 'kopier_orgnr' in x)

                            # Add the text content of the td to the row data
                            text_content = td.get_text(strip=True)
                            if text_content:
                                row_data.append(text_content)

                            # Look for a tags to extract the href attribute
                            a_tag = td.find('a')
                            if a_tag and 'href' in a_tag.attrs:
                                url = a_tag['href']
                                row_data.append(
                                    f'https://w2.brreg.no/kunngjoring/{url}')

                        # Print the row data if it contains relevant information
                        if row_data:
                            
                            row_dict['navn'] = row_data[0]

                            orgnnr = re.sub("[^0-9]", "", row_data[1])
                            row_dict['orgnr'] = orgnnr
                            row_dict['dato'] = self.from_date
                            # row_dict['dato'] = row_data[2]
                            row_dict['type'] = row_data[2]
                            row_dict['url'] = row_data[3]

                            data.append(row_dict)
                            
            if not data:
                self.logger.warning(f'No data found in table rows at {self.url}')
                #raise ValueError(f'No data found in table rows at {self.url}')
                
            df = pd.DataFrame(
                data, columns=['navn', 'orgnr', 'dato', 'type', 'url'])
            df['dato'] = pd.to_datetime(df['dato'], format='%d.%m.%Y')
            
            self.df = df
            
        except Exception as e:
            self.logger.error(f'Failed to parse source content into pandas dataframe at {self.url}')
            return None
                        

    def print_url(self):
        print(type(self.url))


if __name__ == '__main__':
    from_date = datetime.strftime(datetime.now() - timedelta(1), format='%d.%m.%Y')
    to_date = datetime.strftime(datetime.now() - timedelta(1), format='%d.%m.%Y')
    
    job = AnnouncementsScraper(
        from_date = from_date,
        to_date = to_date,
        logger = getLogger(__name__)
        )
    
    #job.fetch_document_content()
    print(type(job.from_date))
    #job.scrape()
    #print(type(job.page_source))
    #print(job.page_source)
    #job.source_to_df()
    
    
