# -*- coding: utf-8 -*-

import json
import glob
import urllib2
import re
import datetime
from bs4 import BeautifulSoup
import codecs
from termcolor import colored
import sys

# ------- CONSTANTS --------- #
KEYWORDS = json.load(open("scrip.json"))

MISC_KEY = "--CHARGES--"

COLUMNS = ['Order No', 'Order Time', 'Trade No.', 'Trade Time', 'Security', 'Bought Qty', 'Sold Qty', 'Gross Rate', 'Gross Total', 'Brokerage', 'Net Rate', 'Service Tax', 'STT', 'Total', 'Trade Date']
COLUMNS_NEW = ['Order No', 'Order Time', 'Trade No.', 'Trade Time', 'Security', 'Buy/Sell', 'Quantity', 'Gross Rate', 'Brokerage', 'Net Rate', 'Closing Rate', 'Total', 'Remarks', 'Trade Date']

BROKERAGE_RATE = 0.004
EXIT_LOAD_RATE = 0.004

BACKLOG = -20000.00

""" Custom class for printing to file
"""
class writer:
    def __init__(self, *writers) :
        self.writers = writers
                        
    def write(self, text) :
        for w in self.writers :
            w.write(text)

""" Get current market price
"""
def get_market_price(symbol):
    print "Getting market price: " + symbol

    base_url = 'http://finance.google.com/finance?q='

    if symbol not in KEYWORDS:
        print "Scrip information not available!"
        
        raise Exception("New Scrip! Add Symbol!")

    symbol = KEYWORDS[symbol]

    try:
        response = urllib2.urlopen(base_url + symbol)
        html = response.read()
    except Exception, msg:
        print msg
        return (0.0, "")

    soup = BeautifulSoup(html)

    try:
        price_change = soup.find("div", { "class": "id-price-change" })
        price_change = price_change.find("span").find_all("span")
        price_change = [x.string for x in price_change]

        price = soup.find_all("span", id=re.compile('^ref_.*_l$'))[0].string
        price = str(unicode(price).encode('ascii', 'ignore')).strip().replace(",", "")

        return (price, price_change)
    except Exception as e:
        print "Can't get current rate for scrip: " + symbol
        return (0.0, "")

""" Get transaction data from Contract Note file
"""
def parse_cn_file(filename):
    print "Processing file: " + filename + "..."
    html = open(filename).read()

    soup = BeautifulSoup(html)

    trade_date = soup.find('td', text = re.compile('TRADE DATE(.*)', re.DOTALL)).parent.findAll('td')[1].text

    table = soup.find("td", class_="xl27boTBL").findParents("table")[0]

    entries = []

    for row in table.findAll("tr"):
        entry = []


        for cell in row.findAll("td"):
            entry.append("".join(c for c in str(unicode(cell.string).encode('ascii', 'ignore')).strip() if c not in "*[]~"))

        # Trade date as last column
        entry.append(datetime.datetime.strftime(datetime.datetime.strptime(trade_date, '%d/%m/%Y'), '%Y-%m-%d'))

        # Filter
        if len(entry) > 11 and "".join(entry):
            entries.append(entry)

        # Ignore rest of the entries
        if "NET AMOUNT DUE" in "".join(entry):
            break

    return entries

""" Process transactions from Contract Notes
"""
def process_cn_entries(entries):
    print "Processing transactions..."

    is_data = False
    is_scrip = False
    is_misc = False
    is_new_html_format = False
    item = {}
    items = []
    misc = {}

    # Prune empty entries
    entries = [entry for entry in entries if "".join(entry).strip()]

    # New format?
    head = entries[0]
    if len(head) == 14:
        is_new_html_format = True

    for entry in entries:
        scrap_entries = [ 'ISIN', 'BUY AVERAGE', 'SELL AVERAGE', 'NET AVERAGE', 'Delivery Total' ]

        # Scrap unnecessary entries
        if any(item in "".join(entry) for item in scrap_entries):
            continue

        # Clean
        entry = [x.strip() for x in entry]

        if entry[0] and entry[0].isdigit():
            is_data = True

        if is_data:
            # New scrip
            if not is_scrip:
                is_scrip = True

                item = {}

                if is_new_html_format:
                    item.update(dict(zip(COLUMNS_NEW, entry)))
                else:
                    item.update(dict(zip(COLUMNS, entry)))

                if is_new_html_format:
                    item['Type'] = "SELL" if item['Buy/Sell'] == 'S' else "BUY"
                else:
                    if 'Sold Qty' in item and item['Sold Qty']:
                        item['Type'] = "SELL"
                        item['Quantity'] = item.pop("Sold Qty")
                    elif 'Bought Qty' in item and item['Bought Qty']:
                        item['Type'] = "BUY"
                        item['Quantity'] = item.pop("Bought Qty")

                # Total is always positive value
                if(float(item['Total']) < 0):
                    item['Total'] = str(abs(float(item['Total'])))

                scrap_keys = COLUMNS[:3]

                if is_new_html_format:
                    scrap_keys += [ 'Buy/Sell', 'Remarks' ]

                item = { key:value for key,value in item.items() if not any(k in key for k in scrap_keys) and value }
            else:
                # Multiple entries
                if entry[0] and entry[0].isdigit():
                    next_item = dict(zip(COLUMNS_NEW, entry))

                    if is_new_html_format:
                        next_item['Type'] = "SELL" if next_item['Buy/Sell'] == 'S' else "BUY"
                    else:
                        if 'Sold Qty' in next_item:
                            next_item['Type'] = "SELL"
                            next_item['Quantity'] = next_item.pop("Sold Qty")

                        if 'Bought Qty' in next_item:
                            next_item['Type'] = "BUY"
                            next_item['Quantity'] = next_item.pop("Bought Qty")

                    # Total is always positive value
                    if(float(next_item['Total']) < 0):
                        next_item['Total'] = str(abs(float(next_item['Total'])))

                    scrap_keys = COLUMNS[:3]

                    if is_new_html_format:
                        scrap_keys += [ 'Buy/Sell', 'Remarks' ]

                    next_item = { key:value for key,value in next_item.items() if not any(k in key for k in scrap_keys) and value }

                    if "Trades" not in item:
                        item = {"Trades": [ item ]}

                    item["Trades"].append(next_item)
                    continue

                col = 11 if is_new_html_format else 12

                if entry[col]:
                    item[entry[4].strip("*").strip()] = entry[col]

                # Finish
                if "TOTAL STT" in entry[4] or not entry[col]:
                    is_scrip = False
                    is_data = False

                    # Cleanup
                    scrap_keys = COLUMNS[:3]
                    scrap_keys += [ 'STT SELL DELIVERY', 'STT BUY DELIVERY' ]

                    if is_new_html_format:
                        scrap_keys += [ 'Buy/Sell', 'Remarks' ]

                    item = { key:value for key,value in item.items() if not any(k in key for k in scrap_keys) and value }

                    if "TOTAL STT" in item:
                        item['STT'] = item.pop("TOTAL STT")

                    items.append(item)

                    if not entry[col]:
                        is_misc = True
        else:
            if items:
                is_misc = True

        # Process MISC entries
        if is_misc:
            col = 11 if is_new_html_format else 13
            if not entry[col - 1] or is_new_html_format:
                misc[entry[4].strip("*").strip("[]").strip("~").strip()] = entry[col]

        # Ignore rest of the entries
        if "NET AMOUNT DUE" in "".join(entry):
            break

    scrap_keys = [ 'NET AMOUNT DUE TO', 'DR. TOTAL', 'CR. TOTAL' ]

    # Misc Charges
    misc = {key:value for key,value in misc.items() if not any(k in key for k in scrap_keys)}
    misc['Total'] = sum(float(item) for key,item in misc.items())
    misc['Type'] = "MISC"
    items.append(misc)

    return items

""" Crunch entries
"""
def crunch_cn_entries(entries):
    crunched_entries = []

    for entry in entries:
        # Expand multiple trade entries
        if "Trades" in entry:
            crunched_entries.extend(entry["Trades"])
        else:
            if entry["Type"] == "MISC":
                misc_entry = { key:value for key,value in entry.items() if key in ["Type", "Total"] }
                crunched_entries.append(misc_entry)
            else:
                crunched_entries.append(entry)

    return crunched_entries

""" Crunch transactions
"""
def crunch_transactions(entries):
    crunched_entries = []

    misc_total = 0

    for entry in entries:
        if entry["Type"] == "MISC":
            misc_total += entry["Total"]
        else:
            if 'STT' in entry:
                del(entry['STT'])
            crunched_entries.append(entry)

    crunched_entries = sorted(crunched_entries, key=lambda k: (k['Security'], k['Trade Date'], k['Type'], k['Trade Time']))

    crunched_entries.append({"Type": "MISC", "Total": misc_total})

    return crunched_entries

""" Crunch trades
"""
def crunch_trades(transactions):
    trades = {}

    # Retreive and clean MISC
    misc_total = transactions[-1]["Total"]
    del(transactions[-1])

    trades[MISC_KEY] = {
            "Total Value": misc_total
            }

    for transaction in transactions:
        scrip = transaction['Security']
        quantity = float(transaction['Quantity'])
        total = float(transaction["Total"])

        # Blank entry
        if scrip not in trades:
            trades[scrip] = {
                "Total Quantity": 0,
                "Total Value": 0,
                "Rate": 0,
                "Cleared": 0
            }


        # BUY
        if transaction['Type'] == 'BUY':
            trades[scrip]['Total Quantity'] += quantity
            trades[scrip]['Total Value'] += total
            trades[scrip]['Rate'] = trades[scrip]['Total Value'] / trades[scrip]['Total Quantity']

        else:
            # Have shares?
            if trades[scrip]['Total Quantity'] >= quantity:
                # Calculate cleared value
                trades[scrip]['Cleared'] += total - (quantity * trades[scrip]['Rate'])

                # The difference is covered by Cleared. Rate remains the same.
                trades[scrip]['Total Quantity'] -= quantity
                trades[scrip]['Total Value'] = trades[scrip]['Total Quantity'] * trades[scrip]['Rate']

        # Prune
        if trades[scrip]['Total Quantity'] == 0:
            if trades[scrip]['Cleared'] == 0:
                del(trades[scrip])
            else:
                trades[scrip]['Rate'] = 0

    return trades

""" Update portfolio with trades
"""
def update_portfolio(trades, portfolio):
    print "Updating portfolio..."

    for scrip in trades:
        if scrip == MISC_KEY:
            continue

        portfolio[scrip] = {
                "Total Quantity": trades[scrip]["Total Quantity"],
                "Total Value": trades[scrip]["Total Value"],
                "Average Rate": trades[scrip]["Rate"],
                "Cleared": trades[scrip]["Cleared"]
                }

    portfolio[MISC_KEY] = {"Total Value": trades[MISC_KEY]["Total Value"]}

""" Create and update the portfolio
"""
def generate_portfolio(transactions):
    print "Generating portfolio..."

    portfolio = {}

    update_portfolio(trades, portfolio)

    report = process_portfolio(portfolio)

    percentage = report['balance'] / report['total'] * 100

    # ------------ Display results --------------
    # ------------ Save results to file --------------
    
    with open('report.txt', 'a') as outfile:
        _saved_stdout = sys.stdout
        sys.stdout = writer(sys.stdout, outfile)
       
        print
        print
        print "+" * 80
        print "-" * 30 + " " + colored(datetime.datetime.strftime(datetime.datetime.now(), "%Y-%m-%d %H:%M:%S"), 'cyan') + " " + "-" * 29
        print "+" * 80

        tabular(portfolio)

        print "=" * 61
        print " | A. TOTAL INVESTMENT       : " + colored("{0:29}".format("₹ {:,.2f}".format(report['total'])), 'white') + " |"
        print " | B. CURRENT VALUE          : " + colored("{0:29}".format("₹ {:,.2f}".format(report['current_value'])), 'yellow') + " |"
        print " | C. ENTRY LOAD (ACTUAL)    : " + colored("{0:29}".format("₹ {:,.2f}".format(report['entry_load'])), 'cyan') + " |"
        print " | D. EXIT LOAD (ESTIMATED)  : " + colored("{0:29}".format("₹ {:,.2f}".format(report['exit_load'])), 'cyan') + " |"
        print " | E. PROFIT/LOSS            : " + colored("{0:29}".format("₹ {:,.2f} ( {:.2f}% )".format(report['balance'], percentage)), "red" if report['balance'] < 0 else "green") + " |"
        print " | F. CLEARED [LESS CHARGES] : " + colored("{0:29}".format("₹ {:,.2f}".format(report['cleared'])), "red" if report['cleared'] < 0 else "green") + " |"
        print " | G. BACKLOG (ACTUAL)       : " + colored("{0:29}".format("₹ {:,.2f}".format(BACKLOG)), 'red') + " |"
        print "=" * 61

        print
        print "+" * 80
        print
        
        sys.stdout = _saved_stdout


""" Report from portfolio
"""
def process_portfolio(portfolio):
    print "Processing portfolio..."

    balance = 0
    total = 0
    current_value = 0
    cleared = 0

    # Final
    for key in dict(portfolio):
        # Misc
        if key == MISC_KEY:
            balance -= portfolio[key]["Total Value"]
            portfolio[key]["Total Value"] = round(portfolio[key]["Total Value"], 2)
        else:
            market_rate = get_market_price(key)
            portfolio[key]["Market Rate"] = float(market_rate[0])
            portfolio[key]["Market Change"] = market_rate[1]

            if portfolio[key]["Total Value"] > 0:
                portfolio[key]["Current Value"] = portfolio[key]["Total Quantity"] * portfolio[key]["Market Rate"]
                portfolio[key]["Profit/Loss"] = portfolio[key]["Current Value"] - portfolio[key]["Total Value"]
                portfolio[key]["ROI"] = portfolio[key]["Profit/Loss"] / portfolio[key]["Total Value"] * 100
                portfolio[key]["Average Rate"] = portfolio[key]["Total Value"] / portfolio[key]["Total Quantity"]
            else:
                portfolio[key]["Current Value"] = 0
                portfolio[key]["Profit/Loss"] = 0
                portfolio[key]["ROI"] = 0
                portfolio[key]["Average Rate"] = 0

            balance += portfolio[key]["Profit/Loss"]
            total += portfolio[key]["Total Value"]
            current_value += portfolio[key]["Current Value"]
            cleared += portfolio[key]["Cleared"]

    entry_load = portfolio[MISC_KEY]["Total Value"] + (total * BROKERAGE_RATE)
    exit_load = current_value * EXIT_LOAD_RATE
    balance -= exit_load

    return {
                "total": total,
                "current_value": current_value,
                "entry_load": entry_load,
                "exit_load": exit_load,
                "balance": balance,
                "cleared": cleared
            }

""" Display the portfolio in tabular form
"""
def tabular(data):
    data_table = convert_to_table(data)

    print
    print
    print_table(data_table)
    print
    print

head = [
        'Scrip',
        'Total Quantity',
        'Total Value',
        'Average Rate',
        'Market Rate',
        'Current Value',
        'Profit/Loss',
        'ROI',
        'Cleared'
        ]

""" Convert dictionary to two-dimentional list
"""
def convert_to_table(data):
    data_table = []

    data_table.append(head)

    for key, value in data.items():
        if key == MISC_KEY:
            continue

        row = []
        row.append(key)
        for k in head:
            if k in value:
                if k == "Market Rate":
                    if value[k] == 0:
                        row.append("_INVALID_")
                    else:
                        row.append('{0:.2f} [ {1:>5} ]'.format(value[k], value["Market Change"][0]))
                else:
                    row.append(value[k])

        data_table.append(row)

    return data_table

""" Print the two dimentional list as a table
"""
def print_table(data_table):
    for entry in data_table[0]:
        print "+ {0:-^20}".format(""),

    print "+"

    is_first = True

    for line in data_table:
        for i, entry in enumerate(line):

            if is_first:
                print "| {0:^20}".format(entry),
            else:
                if entry == 0:
                    print "| " + colored("{0:^20}".format("_._"), 'grey'),
                elif entry == "_INVALID_":
                    print "| " + colored("{0:^20}".format("_INVALID_"), 'red'),
                else:
                    if head[i] == "Profit/Loss" or head[i] == "ROI" or head[i] == "Cleared":
                        if entry < 0:
                            color = 'red'
                        else:
                            color = 'green'
                    else:
                        color = 'white'

                    if head[i] == "Scrip":
                        print "| " + colored("{0:20}".format(entry), color),
                    elif head[i] == "Market Rate":
                        print "| " + colored("{0:>20}".format(entry), color),
                    else:
                        if head[i] == "ROI":
                            print "| " + colored("{0:>20}".format('{0:.2f}%'.format(entry)), color),
                        else:
                            print "| " + colored("{0:>20}".format('{0:.2f}'.format(entry)), color),

        print "|"

        for entry in line:
            print "+ {0:-^20}".format(""),

        print "+"

        is_first = False

""" Main
"""
if __name__ == '__main__':
    transactions = []

    # Parse HTML files
    for filename in glob.glob('*.htm'):
        cn_entries = crunch_cn_entries(process_cn_entries(parse_cn_file(filename)))

        transactions.extend(cn_entries)

    # Standardize transactions
    transactions = crunch_transactions(transactions)

    # Start eating them
    trades = crunch_trades(transactions)

    # Generate the porfolio
    generate_portfolio(trades)
