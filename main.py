import pandas as pd
from datetime import datetime
import os
from dotenv import load_dotenv
load_dotenv()
import os
from supabase import create_client
import ssl
ssl._create_default_https_context = ssl._create_unverified_context
import urllib.request
from bs4 import BeautifulSoup
import translators as ts

import logging
from imp import reload

def initiate_logging(LOG_FILENAME):
    reload(logging)

    formatLOG = '%(asctime)s - %(levelname)s: %(message)s'
    logging.basicConfig(filename=LOG_FILENAME,level=logging.INFO, format=formatLOG)
    logging.info('Program started')

def extract_company_info(new_url):
    try:
        with urllib.request.urlopen(new_url) as response:
            html_detail = response.read()
        soup_detail = BeautifulSoup(html_detail, 'html.parser')
        company_info_divs = soup_detail.find("div", class_="panel-body panel-scroll")

        data = {}
        current_key = None
        current_value = []

        for element in company_info_divs.find_all(['h5', 'p']):
            if element.name == 'h5':
                if current_key is not None:
                    data[current_key] = ', '.join(current_value)
                current_key = element.text
                current_value = []
            elif element.name == 'p':
                if element.find('br'):
                    br_text = ', '.join(element.stripped_strings)
                    current_value.append(br_text)
                else:
                    current_value.append(element.text)

        if current_key is not None:
            data[current_key] = ', '.join(current_value)

        return data
    except Exception as e:
        print(f"Error extracting company info: {str(e)}")
        return {}

if __name__ == '__main__':
    LOG_FILENAME = 'scraper.log'
    initiate_logging(LOG_FILENAME)

    PROXY = os.getenv("PROXY")
    SUPABASE_URL = os.getenv("SUPABASE_URL")
    SUPABASE_KEY = os.getenv("SUPABASE_KEY")

    proxy_support = urllib.request.ProxyHandler({'http': PROXY,'https': PROXY})
    opener = urllib.request.build_opener(proxy_support)
    urllib.request.install_opener(opener)
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

    result = {
        "symbol" : [],
        "ipo_price" : [],
        "underwriter": [],
        "updated_on": [],
        "href" : [],
    }

    update_data = {
        "symbol" : [],
        "ipo_price" : [],
        "underwriter": [],
        "updated_on": [],
    }

    try:
        url = f'https://e-ipo.co.id/en/ipo/index?page=1&per-page=&query=&sort=-updated_at&status_id=5&view=list'
        with urllib.request.urlopen(url) as response:
            html = response.read()
        soup = BeautifulSoup(html, 'html.parser')
        names = []
        names_class = soup.find_all(class_="margin-left10 colorwhite")
        for name in names_class:
            company_name, symbol = name.get_text().replace(" Sharia", "").replace(")", "").split(' (')
            result["symbol"].append(symbol.replace("Closed", "").replace("Book Building","") + ".JK")
        notopmargins = soup.find_all("p", class_="notopmargin")
        nobottommargins = soup.find_all(class_="nobottommargin")
        for top, bottom in zip(notopmargins, nobottommargins):
            if bottom.get_text() == "Final Price": result["ipo_price"].append(top.get_text().replace("IDR\xa0", ""))
        buttons = soup.find_all(class_="button button-3d button-small notopmargin button-rounded button-dirtygreen")
        for button in buttons:
            result["href"].append(button.get("href"))
        
        try:
            company_ipo_price_null = supabase.table('idx_company_profile').select('symbol').filter('ipo_price', 'is', 'null').execute().data
            company_symbols_null_ipo = [d['symbol'] for d in company_ipo_price_null]
        except Exception as e:
            print(f"An exception when supabase: {str(e)}")
            
        try:
            for symbol in result["symbol"]:
                if symbol in company_symbols_null_ipo:
                    idx = result["symbol"].index(symbol)
                    new_url = f"https://e-ipo.co.id{result['href'][idx]}"
                    company_info = extract_company_info(new_url)
                    update_data["symbol"].append(symbol)
                    update_data["ipo_price"].append(result["ipo_price"][idx])
                    update_data["underwriter"].append(company_info['Underwriter(s)'])
                    now = datetime.now()
                    update_data["updated_on"].append(now.strftime("%Y-%m-%d %H:%M:%S"))
        except Exception as e:
            print(f"An exception when retrieve data: {str(e)}")
            logging.info(f"An exception when retrieve data: {str(e)}")
            
        # Updating ipo price
        for symbol, ipo_price, underwriter, updated_on in zip(update_data["symbol"], update_data["ipo_price"], update_data["underwriter"], update_data["updated_on"]):
            try:
                supabase.table('idx_company_profile').update({
                    'ipo_price': ipo_price,
                    'underwriter': underwriter,
                    'updated_on': updated_on
                    }).eq('symbol', symbol).execute()
                print("Symbol updated successfully for: ", symbol)
                logging.info(f"Symbol updated successfully for: {symbol}")
            except Exception as e:
                print(f"Error updating data: {str(e)}")
                logging.info(f"Error updating data: {str(e)}")

    except Exception as e:
        print(f"An exception occurred: {str(e)}")
        logging.info(f"An exception occurred: {str(e)}")

    logging.info(f"Finish scrape {len(update_data['ipo_price'])} closed ipo data")