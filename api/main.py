import json
import re
import requests
from bs4 import BeautifulSoup
from typing import Dict

# Global storage for stock names and their target prices
stock_watchlist: Dict[str, float] = {}

class StockMonitor:
    def extract_price_from_html(self, html_content: str) -> float:
        """Extract stock price from Stockbit HTML"""
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            # Look for the price element
            price_element = soup.find('h3', class_=re.compile(r'.*dyRciG.*'))
            if price_element:
                price_text = price_element.get_text().strip()
                # Remove commas and convert to float
                price_text = price_text.replace(',', '')
                return float(price_text)
        except Exception as e:
            print(f"Error extracting price: {e}")
        return 0.0

    def get_stock_price(self, stock_symbol: str) -> float:
        """Fetch stock price from Stockbit"""
        try:
            url = f"https://stockbit.com/symbol/{stock_symbol}"
            response = requests.get(url, timeout=30)
            if response.status_code == 200:
                html_content = response.text
                return self.extract_price_from_html(html_content)
        except Exception as e:
            print(f"Error fetching price for {stock_symbol}: {e}")
        return 0.0

    def send_sell_request(self, stock_symbol: str):
        """Send sell request to the specified endpoint"""
        try:
            url = f"http://danda.fi.da/jual={stock_symbol}"
            response = requests.get(url, timeout=30)
            print(f"Sell request sent for {stock_symbol}, status: {response.status_code}")
            return response.status_code == 200
        except Exception as e:
            print(f"Error sending sell request for {stock_symbol}: {e}")
            return False

# Global monitor instance
monitor = StockMonitor()

def check_and_process_stocks() -> dict:
    """Check all stocks and process sells if needed"""
    if not stock_watchlist:
        return {"message": "No stocks in watchlist"}

    results = []
    stocks_to_remove = []

    for stock_symbol, target_price in stock_watchlist.items():
        try:
            current_price = monitor.get_stock_price(stock_symbol)
            if current_price > 0:
                # Calculate percentage difference
                price_diff_percent = ((target_price - current_price) / target_price) * 100
                result = {
                    "stock": stock_symbol,
                    "current_price": current_price,
                    "target_price": target_price,
                    "difference_percent": round(price_diff_percent, 2)
                }

                # If current price is below 1% of target price
                if price_diff_percent >= 1.0:
                    sell_success = monitor.send_sell_request(stock_symbol)
                    result["sell_triggered"] = True
                    result["sell_success"] = sell_success

                    if sell_success:
                        stocks_to_remove.append(stock_symbol)
                else:
                    result["sell_triggered"] = False

                results.append(result)

        except Exception as e:
            results.append({"stock": stock_symbol, "error": str(e)})

    # Remove sold stocks from watchlist
    for stock in stocks_to_remove:
        del stock_watchlist[stock]

    return {
        "results": results,
        "remaining_watchlist": stock_watchlist
    }

def handler(request):
    """Main request handler for Vercel"""
    try:
        method = request['httpMethod']
        path = request['path']
        body = request.get('body', '')

        if method == 'GET':
            if path == '/restart':
                return handle_restart()
            elif 'stockName=' in path:
                return handle_add_stock(path)
            elif path == '/check':
                return handle_check_stocks()
            else:
                return {
                    'statusCode': 404,
                    'body': json.dumps({'message': 'Not found'})
                }
        
        elif method == 'POST':
            return {
                'statusCode': 200,
                'body': json.dumps({"message": "POST received"})
            }

    except Exception as e:
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }

def handle_restart():
    """Handle restart endpoint - clear stock watchlist"""
    global stock_watchlist
    stock_watchlist.clear()
    return {
        'statusCode': 200,
        'body': json.dumps({'message': 'Stock watchlist cleared', 'watchlist': stock_watchlist})
    }

def handle_add_stock(path):
    """Handle adding stock to watchlist"""
    global stock_watchlist
    try:
        stock_match = re.search(r'stockName=([A-Z]{3,4})', path)
        if not stock_match:
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'Invalid stock name format. Use 3-4 letter code.'})
            }

        stock_symbol = stock_match.group(1)

        # Extract price from query
        price_match = re.search(r'price=([0-9.]+)', path)
        if not price_match:
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'Price parameter is required'})
            }

        target_price = float(price_match.group(1))

        # Add to watchlist
        stock_watchlist[stock_symbol] = target_price

        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': f'Added {stock_symbol} to watchlist',
                'stock': stock_symbol,
                'target_price': target_price,
                'watchlist': stock_watchlist
            })
        }

    except Exception as e:
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }

def handle_check_stocks():
    """Handle manual stock checking"""
    try:
        result = check_and_process_stocks()
        return {
            'statusCode': 200,
            'body': json.dumps(result)
        }

    except Exception as e:
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }

# Entry point for Vercel
app = handler
