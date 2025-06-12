# api/main.py (This should be placed in api/ folder)
import asyncio
import aiohttp
import re
from urllib.parse import parse_qs, urlparse
from typing import Dict, List
import json
import time
from bs4 import BeautifulSoup

# Global storage for stock names and their target prices
stock_watchlist: Dict[str, float] = {}

class StockMonitor:
    def __init__(self):
        self.session = None
        self.monitoring = False
    
    async def get_session(self):
        if self.session is None:
            self.session = aiohttp.ClientSession()
        return self.session
    
    async def close_session(self):
        if self.session:
            await self.session.close()
            self.session = None
    
    async def extract_price_from_html(self, html_content: str) -> float:
        """Extract stock price from Stockbit HTML"""
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Look for the price element - multiple approaches
            # Method 1: Find h3 with the specific classes
            price_element = soup.find('h3', class_=re.compile(r'.*dyRciG.*'))
            
            if price_element:
                price_text = price_element.get_text().strip()
                # Remove commas and convert to float
                price_text = price_text.replace(',', '')
                try:
                    return float(price_text)
                except ValueError:
                    pass
            
            # Method 2: Search for pattern in the example (2,120)
            # Look for numbers that appear to be prices
            price_patterns = [
                r'<h3[^>]*>(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)</h3>',
                r'>(\d{1,3}(?:,\d{3})*)<',
                r'(\d{1,4}(?:,\d{3})*)'
            ]
            
            for pattern in price_patterns:
                matches = re.findall(pattern, html_content)
                if matches:
                    for match in matches:
                        try:
                            price_str = match.replace(',', '')
                            price = float(price_str)
                            # Reasonable price range check (between 1 and 100000)
                            if 1 <= price <= 100000:
                                return price
                        except ValueError:
                            continue
                            
        except Exception as e:
            print(f"Error extracting price: {e}")
        
        return 0.0
    
    async def get_stock_price(self, stock_symbol: str) -> float:
        """Fetch stock price from Stockbit"""
        try:
            session = await self.get_session()
            url = f"https://stockbit.com/symbol/{stock_symbol}"
            
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as response:
                if response.status == 200:
                    html_content = await response.text()
                    return await self.extract_price_from_html(html_content)
                    
        except Exception as e:
            print(f"Error fetching price for {stock_symbol}: {e}")
        
        return 0.0
    
    async def send_sell_request(self, stock_symbol: str):
        """Send sell request to the specified endpoint"""
        try:
            session = await self.get_session()
            url = f"http://engaging-purely-rabbit.ngrok-free.app/jual={stock_symbol}"
            
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as response:
                print(f"Sell request sent for {stock_symbol}, status: {response.status}")
                return response.status == 200
                
        except Exception as e:
            print(f"Error sending sell request for {stock_symbol}: {e}")
            return False

# Global monitor instance
monitor = StockMonitor()

async def check_and_process_stocks():
    """Check all stocks and process sells if needed"""
    if not stock_watchlist:
        return {"message": "No stocks in watchlist"}
    
    results = []
    stocks_to_remove = []
    
    for stock_symbol, target_price in stock_watchlist.items():
        try:
            current_price = await monitor.get_stock_price(stock_symbol)
            
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
                    sell_success = await monitor.send_sell_request(stock_symbol)
                    result["sell_triggered"] = True
                    result["sell_success"] = sell_success
                    
                    if sell_success:
                        stocks_to_remove.append(stock_symbol)
                else:
                    result["sell_triggered"] = False
                
                results.append(result)
                
        except Exception as e:
            results.append({
                "stock": stock_symbol,
                "error": str(e)
            })
    
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
        # Get request details
        method = getattr(request, 'method', 'GET')
        
        # Handle URL parsing for different frameworks
        if hasattr(request, 'url'):
            if hasattr(request.url, 'path'):
                path = request.url.path
                query = getattr(request.url, 'query', '')
            else:
                path = str(request.url).split('?')[0]
                query = str(request.url).split('?')[1] if '?' in str(request.url) else ''
        else:
            path = getattr(request, 'path', '/')
            query = getattr(request, 'query_string', b'').decode() if hasattr(request, 'query_string') else ''
        
        print(f"Request: {method} {path} Query: {query}")
        
        # Handle different endpoints
        if path == '/restart' or path.endswith('/restart'):
            return handle_restart()
        elif 'stockName=' in path:
            return handle_add_stock(path, query)
        elif path == '/check' or path.endswith('/check'):
            # Manual check endpoint
            return handle_check_stocks()
        else:
            return {
                'statusCode': 200,
                'headers': {'Content-Type': 'application/json'},
                'body': json.dumps({
                    'message': 'Stock Monitor API',
                    'endpoints': {
                        '/restart': 'Clear watchlist',
                        '/stockName=XXXX?price=YYYY': 'Add stock to watchlist',
                        '/check': 'Manually check all stocks'
                    },
                    'current_watchlist': stock_watchlist
                })
            }
            
    except Exception as e:
        return {
            'statusCode': 500,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'error': str(e)})
        }

def handle_restart():
    """Handle restart endpoint - clear stock watchlist"""
    global stock_watchlist
    
    stock_watchlist.clear()
    
    return {
        'statusCode': 200,
        'headers': {'Content-Type': 'application/json'},
        'body': json.dumps({
            'message': 'Stock watchlist cleared',
            'watchlist': stock_watchlist
        })
    }

def handle_add_stock(path, query):
    """Handle adding stock to watchlist"""
    global stock_watchlist
    
    try:
        # Extract stock symbol from path
        stock_match = re.search(r'stockName=([A-Z]{3,4})', path)
        if not stock_match:
            return {
                'statusCode': 400,
                'headers': {'Content-Type': 'application/json'},
                'body': json.dumps({'error': 'Invalid stock name format. Use 3-4 letter code.'})
            }
        
        stock_symbol = stock_match.group(1)
        
        # Parse price from query
        price_match = re.search(r'price=([0-9.]+)', query)
        if not price_match:
            return {
                'statusCode': 400,
                'headers': {'Content-Type': 'application/json'},
                'body': json.dumps({'error': 'Price parameter is required'})
            }
        
        try:
            target_price = float(price_match.group(1))
        except ValueError:
            return {
                'statusCode': 400,
                'headers': {'Content-Type': 'application/json'},
                'body': json.dumps({'error': 'Invalid price format'})
            }
        
        # Add to watchlist
        stock_watchlist[stock_symbol] = target_price
        
        return {
            'statusCode': 200,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({
                'message': f'Added {stock_symbol} to watchlist',
                'stock': stock_symbol,
                'target_price': target_price,
                'watchlist': stock_watchlist,
                'note': 'Use /check endpoint to manually trigger price checks'
            })
        }
        
    except Exception as e:
        return {
            'statusCode': 500,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'error': str(e)})
        }

def handle_check_stocks():
    """Handle manual stock checking"""
    try:
        # Run the async function
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(check_and_process_stocks())
        
        return {
            'statusCode': 200,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps(result)
        }
        
    except Exception as e:
        return {
            'statusCode': 500,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'error': str(e)})
        }
    finally:
        try:
            loop.close()
        except:
            pass

# Default handler for Vercel
def app(request):
    return handler(request)

# Alternative entry points
main = app
index = app
