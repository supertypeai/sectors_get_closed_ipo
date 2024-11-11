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
        ipo_detail_divs = soup_detail.find("div", class_="list-group")

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
                    
        for element in ipo_detail_divs.find_all(['h5', 'p']):
            if element.name == "h5":
                    current_key = element.text
            if element.name == "p":
                if current_key == "Book Building": 
                    if "IDR" in element.text:
                        data["book_building_lower_bound"] = int(element.text.split(" - ")[0].split("IDR\xa0")[1].replace(",","").replace(".",""))
                        data["book_building_upper_bound"] = int(element.text.split(" - ")[1].split("IDR\xa0")[1].replace(",","").replace(".",""))
                    else:
                        data["book_building_start_date"] = datetime.strptime(element.text.split(" - ")[0], "%d %b %Y").strftime("%Y-%m-%d")
                        data["book_building_end_date"] = datetime.strptime(element.text.split(" - ")[1], "%d %b %Y").strftime("%Y-%m-%d")
                if current_key == "Offering":
                    if "IDR" in element.text:
                        data["offering_price"] = int(element.text.split("IDR\xa0")[1].replace(",","").replace(".",""))
                    else:
                        data["offering_start_date"] = datetime.strptime(element.text.split(" - ")[0], "%d %b %Y").strftime("%Y-%m-%d")
                        data["offering_end_date"] = datetime.strptime(element.text.split(" - ")[1], "%d %b %Y").strftime("%Y-%m-%d")
                        data["closing_date"] = datetime.strptime(element.text.split(" - ")[1], "%d %b %Y").strftime("%Y-%m-%d")
                if current_key == "Distribution":
                    data["distribution_date"] = datetime.strptime(element.text, "%d %b %Y").strftime("%Y-%m-%d")
                if current_key == "Prospectus":
                    data["prospectus_url"] = "https://e-ipo.co.id" + element.select("a[data-content='Download Prospectus']")[0].get("href")
                if current_key == "Additional Information":
                    data["additional_info_url"] = "https://e-ipo.co.id" + element.select("a[data-content='Download Additional Information']")[0].get("href")

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
    
    ipo_details = {
        "symbol": [],
        "company_name": [],
        "shares_offered": [],
        "percent_total_shares":[],
        "book_building_start_date":[],
        "book_building_end_date":[],
        "book_building_lower_bound":[],
        "book_building_upper_bound":[],
        "offering_start_date":[],
        "offering_end_date":[],
        "offering_price":[],
        "closing_date":[],
        "distribution_date":[],
        "prospectus_url":[],
        "additional_info_url":[],
        "updated_at": []
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
            company_ipo_price_null = supabase.table('idx_company_profile_2024_11_11').select('symbol, company_name').filter('ipo_price', 'is', 'null').execute().data
            company_symbols_null_ipo = {d['symbol']: d['company_name'] for d in company_ipo_price_null}
        except Exception as e:
            print(f"An exception when supabase: {str(e)}")
            
        try:
            for symbol in result["symbol"]:
                if symbol in company_symbols_null_ipo.keys():
                    idx = result["symbol"].index(symbol)
                    new_url = f"https://e-ipo.co.id{result['href'][idx]}"
                    company_info = extract_company_info(new_url)
                    update_data["symbol"].append(symbol)
                    update_data["ipo_price"].append(result["ipo_price"][idx])
                    update_data["underwriter"].append(company_info['Underwriter(s)'])
                    now = datetime.now()
                    update_data["updated_on"].append(now.strftime("%Y-%m-%d %H:%M:%S"))
                    
                    ipo_details["symbol"].append(symbol)
                    ipo_details["company_name"].append(company_symbols_null_ipo[symbol])
                    ipo_details["shares_offered"].append(company_info['Number of shares offered'].replace(" shares", "").replace(",", ""))
                    ipo_details["percent_total_shares"].append(float(company_info['% of Total Shares']) / 100)
                    ipo_details["book_building_start_date"].append(company_info["book_building_start_date"])
                    ipo_details["book_building_end_date"].append(company_info["book_building_end_date"])
                    ipo_details["book_building_lower_bound"].append(company_info["book_building_lower_bound"])
                    ipo_details["book_building_upper_bound"].append(company_info["book_building_upper_bound"])
                    ipo_details["offering_start_date"].append(company_info["offering_start_date"])
                    ipo_details["offering_end_date"].append(company_info["offering_end_date"])
                    ipo_details["offering_price"].append(company_info["offering_price"])
                    ipo_details["closing_date"].append(company_info["closing_date"])
                    ipo_details["distribution_date"].append(company_info["distribution_date"])
                    ipo_details["prospectus_url"].append(company_info["prospectus_url"])
                    ipo_details["additional_info_url"].append(company_info["additional_info_url"])
                    ipo_details["updated_at"].append(now.strftime("%Y-%m-%d %H:%M:%S"))
                    print(ipo_details)
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
                print("Company profile updated successfully for: ", symbol)
                logging.info(f"Company profile updated successfully for: {symbol}")
                
            except Exception as e:
                print(f"Error updating data: {str(e)}")
                logging.info(f"Error updating data: {str(e)}")
        
        for symbol, company_name, shares_offered, percent_total_shares, book_building_start_date, book_building_end_date, book_building_lower_bound, book_building_upper_bound, offering_start_date, offering_end_date, offering_price, closing_date, distribution_date, prospectus_url, additional_info_url, updated_at in zip(ipo_details["symbol"], ipo_details['company_name'], ipo_details["shares_offered"], ipo_details["percent_total_shares"], ipo_details["book_building_start_date"], ipo_details["book_building_end_date"], ipo_details["book_building_lower_bound"], ipo_details["book_building_upper_bound"], ipo_details["offering_start_date"], ipo_details["offering_end_date"], ipo_details["offering_price"], ipo_details["closing_date"], ipo_details["distribution_date"], ipo_details["prospectus_url"], ipo_details["additional_info_url"], ipo_details["updated_at"]):
            try:
                supabase.table('idx_ipo_details').upsert({
                    'symbol': symbol,
                    'company_name': company_name,
                    'shares_offered': shares_offered,
                    'percent_total_shares': percent_total_shares,
                    'book_building_start_date': book_building_start_date,
                    'book_building_end_date': book_building_end_date,
                    'book_building_lower_bound': book_building_lower_bound,
                    'book_building_upper_bound': book_building_upper_bound,
                    'offering_start_date': offering_start_date,
                    'offering_end_date': offering_end_date,
                    'offering_price': offering_price,
                    'closing_date': closing_date,
                    'distribution_date': distribution_date,
                    'prospectus_url': prospectus_url,
                    'additional_info_url': additional_info_url,
                    'updated_at': updated_at
                }).execute()
                print("IPO detail updated successfully for: ", symbol)
                logging.info(f"IPO detail updated successfully for: {symbol}")
            except Exception as e:
                print(f"Error updating data: {e}")
                logging.info(f"Error updating data: {e}")
            

    except Exception as e:
        logging.info(f"An exception occurred: {str(e)}")
        raise Exception(f"An exception occurred: {str(e)}")

    logging.info(f"Finish scrape {len(update_data['ipo_price'])} closed ipo data")