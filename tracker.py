# -*- coding: utf-8 -*-

import json
import glob
import urllib2
import re
import datetime
from bs4 import BeautifulSoup
from termcolor import colored
import sys

# ------- CONSTANTS --------- #
MISC_KEY = "--CHARGES--"

COLUMNS = ['Order No', 'Order Time', 'Trade No.', 'Trade Time', 'Security', 'Bought Qty', 'Sold Qty', 'Gross Rate', 'Gross Total', 'Brokerage', 'Net Rate', 'Service Tax', 'STT', 'Total', 'Trade Date']
COLUMNS_NEW = ['Order No', 'Order Time', 'Trade No.', 'Trade Time', 'Security', 'Buy/Sell', 'Quantity', 'Gross Rate', 'Brokerage', 'Net Rate', 'Closing Rate', 'Total', 'Remarks', 'Trade Date']
LEDGER_COLUMNS = ['Date', 'Voucher', 'Bank Code', 'Cheque', 'Description', 'Debit', 'Credit', 'Balance']

# Title, Width, Alignment, Key, IsNumber, IsCurrency, Color
REPORT_FORMAT = [
        ('Security', 20, '<', '', False, False, 'white'),
        ('Quantity', 11, '>', 'Total Quantity', True, False, 'white'),
        ('Buy Value', 14, '>', 'Total Value', True, True, 'white'),
        ('Rate', 12, '>', 'Average Rate', True, True, 'white'),
        ('New Rate', 12, '>', 'Market Rate', True, True, 'white'),
        ('Rate Change', 18, '>', 'Market Change', True, True, ('red', 'green')),
        ('New Value', 14, '>', 'Current Value', True, True, 'white'),
        ('Profit/Loss', 23, '>', 'Profit/Loss', True, True, ('red', 'green')),
        ('Cleared', 22, '>', 'Cleared', True, True, ('red', 'green')),
        ('Intraday', 22, '>', 'Intraday', True, True, ('red', 'green')),
        ('Dividend', 10, '>', 'Dividend', True, True, 'white')
        ]

'''
Current Value
Cleared Percentage
Market Change
Average Rate
Total Brokerage
Total Trade Volume
Total Quantity
Intraday Percentage
Total Value
Profit/Loss Percentage
Dividend
Cleared
Profit/Loss
Intraday
Market Rate
'''
REPORT_ORDER = {
        "sort_key": "",
        "reverse": False,
        "blank_at_end": True
        }

# 0.3% - 0.4% (0.2% minimum limit for accomodating rounding)
BROKERAGE_RATE_DELIVERY = 0.002

EXIT_LOAD_RATE = 0.004
CAPITAL_GAIN_TAX_RATE = 0.15

PREVIOUS_BALANCE = -20000.00

SELL_RECOMMENDATION_CUTOFF = 4.0
SELL_RECOMMENDATION_RATE = 105.8/100

# ------- GLOBALS --------- #
dividends = []
ipo_investment = 0


class Writer:
    """ Custom class for printing to file
    """
    def __init__(self, *writers):
        self.writers = writers

    def write(self, text):
        for w in self.writers:
            w.write(text)


class ScripManager:
    """ Class for managing scrips
    """
    URL = "http://finance.google.com/finance/info?q="

    def __init__(self):
        self.title = {}
        self.scrip = {}

        self.load_titles()
        self.fetch_price()

    def get_scrip_from_title(self, title):
        if title not in self.title:
            raise Exception("New Scrip! Add to scrip.json! [ {} ]".format(title))

        return self.title[title]

    def get_title_from_scrip(self, scrip):
        return self.scrip[scrip]['title']

    def get_price(self, scrip):
        scrip = self.scrip[scrip]

        price = float(scrip['price'])
        price_change = [
            float(scrip['change']),
            float(scrip['change_percentage'])
        ]

        return (price, price_change)

    def load_titles(self):
        # List of titles
        self.title = json.load(open("scrip.json"))

        for k, v in self.title.items():
            self.scrip[v] = {'title': k}

    def fetch_price(self):
        scrip_list = ",".join(self.scrip.keys())

        url = ScripManager.URL + scrip_list

        response = urllib2.urlopen(url).read()

        # Remove leading '//'
        response = response[4:]

        response = json.loads(response)

        # Let's parse
        for item in response:
            scrip = item['e'] + ':' + item['t']

            # FIXME : Kludge
            if scrip == "BOM:532285":
                scrip = "NSE:GEOJITBNPP"

            self.scrip[scrip]['price'] = item['l'].replace(',', '')
            self.scrip[scrip]['change'] = (item['c'].replace(',', '')
                                           if item['c']
                                           else "0")
            self.scrip[scrip]['change_percentage'] = (item['cp'].replace(',', '')
                                                      if item['cp']
                                                      else "0")


def parse_cn_file(filename):
    """ Get transaction data from Contract Note file
    """
    print "Processing file: " + filename + "..."
    html = open(filename).read()

    soup = BeautifulSoup(html, 'lxml')

    trade_date = soup.find('td', text=re.compile('TRADE DATE(.*)', re.DOTALL)).parent.findAll('td')[1].text

    table = soup.find("td", class_="xl27boTBL").findParents("table")[0]

    entries = []

    # Just read all rows first
    for row in table.findAll("tr"):
        entry = []

        for cell in row.findAll("td"):
            entry.append("".join(c for c in str(unicode(cell.string).encode('ascii', 'ignore')).strip() if c not in "*[]~"))

        # Trade date as last column
        entry.append(datetime.datetime.strftime(datetime.datetime.strptime(trade_date, '%d/%m/%Y'), '%Y-%m-%d'))

        # Filter
        if len(entry) > 11 and "".join(entry):
            entries.append(entry)

    # Delete unwanted entries
    for entry in reversed(entries):
        if "NET AMOUNT DUE" not in "".join(entry):
            entries.pop()
        else:
            break

    return entries


def process_cn_entry(entry, is_new_html_format=False):
    """ Process a single entry from CN
    """
    processed_entry = {}

    if is_new_html_format:
        processed_entry.update(dict(zip(COLUMNS_NEW, entry)))
    else:
        processed_entry.update(dict(zip(COLUMNS, entry)))

    if is_new_html_format:
        processed_entry['Type'] = "SELL" if processed_entry['Buy/Sell'] == 'S' else "BUY"
    else:
        if 'Sold Qty' in processed_entry and processed_entry['Sold Qty']:
            processed_entry['Type'] = "SELL"
            processed_entry['Quantity'] = processed_entry.pop("Sold Qty")
        elif 'Bought Qty' in processed_entry and processed_entry['Bought Qty']:
            processed_entry['Type'] = "BUY"
            processed_entry['Quantity'] = processed_entry.pop("Bought Qty")

    # Total is always positive value
    if(float(processed_entry['Total']) < 0):
        processed_entry['Total'] = str(abs(float(processed_entry['Total'])))

    # Is this intraday?
    brokerage_rate = float(processed_entry['Brokerage']) / float(processed_entry['Gross Rate'])

    if brokerage_rate < BROKERAGE_RATE_DELIVERY:
        processed_entry['Intraday'] = True
    else:
        processed_entry['Intraday'] = False

    processed_entry['Scrip'] = scrip_manager.get_scrip_from_title(processed_entry['Security'])

    scrap_keys = COLUMNS[:3]

    if is_new_html_format:
        scrap_keys += ['Buy/Sell', 'Remarks']

    # Scrap
    processed_entry = {key:value for key,value in processed_entry.items() if not any(k in key for k in scrap_keys) and (key == 'Intraday' or value)}

    return processed_entry


def process_cn_entries(entries):
    """ Process transactions from Contract Notes
    """
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
    if len(entries[0]) == 14:
        is_new_html_format = True

    for entry in entries:
        scrap_entries = ['ISIN', 'BUY AVERAGE', 'SELL AVERAGE', 'NET AVERAGE', 'Delivery Total']

        # Scrap unnecessary entries
        if any(item in "".join(entry) for item in scrap_entries):
            continue

        # Clean
        entry = [x.strip() for x in entry]

        if entry[0] and entry[0].isdigit():
            is_data = True

        if is_data:
            # Scrip entries start
            if not is_scrip:
                is_scrip = True

                item = process_cn_entry(entry, is_new_html_format)
            else:
                # More entries for same scrip
                if entry[0] and entry[0].isdigit():
                    next_item = process_cn_entry(entry, is_new_html_format)

                    # Move the first entry as first entry in Trades
                    if "Trades" not in item:
                        item = {"Trades": [item]}

                    item["Trades"].append(next_item)

                    # Let's continue on to next entry
                    continue

                col = 11 if is_new_html_format else 12

                if entry[col]:
                    item[entry[4].strip("*").strip()] = entry[col]

                # Entries for the scrip are done
                if "TOTAL STT" in entry[4] or not entry[col]:
                    is_scrip = False
                    is_data = False

                    # Cleanup
                    scrap_keys = COLUMNS[:3]
                    scrap_keys += ['STT SELL DELIVERY', 'STT BUY DELIVERY']

                    if is_new_html_format:
                        scrap_keys += ['Buy/Sell', 'Remarks']

                    item = {key: value for key, value in item.items() if not any(k in key for k in scrap_keys) and value}

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

        # Maybe there is entries from next Exchange after this?
        if "NET AMOUNT DUE" in "".join(entry):
            is_misc = False

    scrap_keys = ['NET AMOUNT DUE TO', 'DR. TOTAL', 'CR. TOTAL']

    # Misc Charges
    misc = {key: value for key, value in misc.items() if not any(k in key for k in scrap_keys)}
    misc['Total'] = sum(float(item) for key, item in misc.items())
    misc['Type'] = MISC_KEY
    items.append(misc)

    return items


def crunch_cn_entries(entries):
    """ Crunch entries
    """
    crunched_entries = []

    for entry in entries:
        # Expand multiple trade entries
        if "Trades" in entry:
            crunched_entries.extend(entry["Trades"])
        else:
            if entry["Type"] == "MISC":
                misc_entry = {key: value for key, value in entry.items() if key in ["Type", "Total"]}
                crunched_entries.append(misc_entry)
            else:
                crunched_entries.append(entry)

    return crunched_entries


def crunch_transactions(entries):
    """ Crunch transactions
    """
    global ipo_investment

    crunched_entries = []

    misc_total = 0

    for entry in entries:
        if entry["Type"] == MISC_KEY:
            misc_total += entry["Total"]
        else:
            if 'STT' in entry:
                del(entry['STT'])

            if 'Scrip' not in entry:
                entry['Scrip'] = scrip_manager.get_scrip_from_title(entry['Security'])

            crunched_entries.append(entry)

        # IPOs
        if "Notes" in entry and entry["Notes"] == "IPO":
            ipo_investment += float(entry["Total"])

    crunched_entries = sorted(crunched_entries, key=lambda k: (k['Scrip'], k['Trade Date'], k['Trade Time']))

    crunched_entries.append({"Type": MISC_KEY, "Total": misc_total})

    return crunched_entries


def calculate_profit(buy_value, sell_value):
    """ Calculate profit for a trade
    """
    profit = sell_value - buy_value
    profit_percentage = profit / buy_value * 100

    return (profit, profit_percentage)


def crunch_trades(transactions):
    """ Crunch trades
    """
    trades = {}

    # Retreive and clean MISC
    misc_total = transactions[-1]["Total"]
    del(transactions[-1])

    trades[MISC_KEY] = {
            "Total Value": misc_total
            }

    for transaction in transactions:
        scrip = transaction['Scrip']
        quantity = float(transaction['Quantity'])
        total = float(transaction["Total"])

        # Blank entry
        if scrip not in trades:
            trades[scrip] = {
                "Total Quantity": 0,
                "Total Value": 0,
                "Rate": 0,
                "Cleared": 0,
                "Cleared Percentage": 0,
                "Intraday Cleared": 0,
                "Intraday Cleared Percentage": 0,
                "Total Buy Value": 0,
                "Total Sell Value": 0,
                "Short Quantity": 0,
                "Short Value": 0,
                "Short Rate": 0,
                "Intraday Buy Value": 0,
                "Intraday Sell Value": 0,
                "Total Trade Volume": 0,
                "Total Brokerage": 0
            }

        # BUY
        if transaction['Type'] == 'BUY':
            # If intraday, just add to total intraday values
            if 'Intraday' in transaction and transaction['Intraday']:
                trades[scrip]['Intraday Buy Value'] += total
            else:
                if trades[scrip]['Short Quantity'] == 0:
                    trades[scrip]['Total Quantity'] += quantity
                    trades[scrip]['Total Value'] += total
                    trades[scrip]['Rate'] = trades[scrip]['Total Value'] / trades[scrip]['Total Quantity']
                else:
                    # Cover short
                    if trades[scrip]['Short Quantity'] >= quantity:
                        # Not enough to cover all
                        trades[scrip]['Total Buy Value'] += total
                        trades[scrip]['Total Sell Value'] += (quantity * trades[scrip]['Short Rate'])

                        trades[scrip]['Short Quantity'] -= quantity
                        trades[scrip]['Short Value'] = trades[scrip]['Short Quantity'] * trades[scrip]['Short Rate']
                    else:
                        # Cover short first
                        cover_quantity = trades[scrip]['Short Quantity']

                        trades[scrip]['Total Buy Value'] += (cover_quantity * total / quantity)
                        trades[scrip]['Total Sell Value'] += (cover_quantity * trades[scrip]['Short Rate'])

                        trades[scrip]['Short Quantity'] = 0
                        trades[scrip]['Short Value'] = 0

                        # Add rest to stock
                        buy_quantity = quantity - cover_quantity
                        trades[scrip]['Total Quantity'] += buy_quantity
                        trades[scrip]['Total Value'] += (buy_quantity * total / quantity)
                        trades[scrip]['Rate'] = trades[scrip]['Total Value'] / trades[scrip]['Total Quantity']
        else:
            # If intraday, just add to total intraday values
            if 'Intraday' in transaction and transaction['Intraday']:
                trades[scrip]['Intraday Sell Value'] += total
            else:
                # Have shares?
                if trades[scrip]['Total Quantity'] >= quantity:
                    # Calculate cleared value
                    trades[scrip]['Total Buy Value'] += quantity * trades[scrip]['Rate']
                    trades[scrip]['Total Sell Value'] += total

                    # The difference is the profit/loss. Rate remains the same.
                    trades[scrip]['Total Quantity'] -= quantity
                    trades[scrip]['Total Value'] = trades[scrip]['Total Quantity'] * trades[scrip]['Rate']
                elif trades[scrip]['Total Quantity'] == 0:
                    trades[scrip]['Short Quantity'] += quantity
                    trades[scrip]['Short Value'] += total
                    trades[scrip]['Short Rate'] = trades[scrip]['Short Value'] / trades[scrip]['Short Quantity']
                else:
                    # Partial short
                    cleared_quantity = trades[scrip]['Total Quantity']

                    trades[scrip]['Total Buy Value'] += trades[scrip]['Total Value']
                    trades[scrip]['Total Sell Value'] += (cleared_quantity * total / quantity)

                    trades[scrip]['Total Quantity'] = 0
                    trades[scrip]['Total Value'] = 0

                    trades[scrip]['Short Quantity'] += quantity - cleared_quantity
                    trades[scrip]['Short Value'] += total - (cleared_quantity * total / quantity)
                    trades[scrip]['Short Rate'] = trades[scrip]['Short Value'] / trades[scrip]['Short Quantity']

        trades[scrip]['Total Trade Volume'] += total

        trades[scrip]['Total Brokerage'] += float(transaction["Brokerage"]) * quantity

        # Prune
        if (trades[scrip]['Total Quantity'] == 0 and
                trades[scrip]['Short Quantity'] == 0 and
                trades[scrip]['Intraday Buy Value'] == 0 and
                trades[scrip]['Intraday Sell Value'] == 0 and
                trades[scrip]['Total Buy Value'] == 0):
            raise Exception('Boo')
            del(trades[scrip])

        # Clean
        if trades[scrip]['Total Quantity'] == 0:
            trades[scrip]['Rate'] = 0

        if trades[scrip]['Short Quantity'] == 0:
            trades[scrip]['Short Rate'] = 0

    # How much did we clear?
    for k, v in trades.items():
        if k == MISC_KEY:
            continue

        if v['Total Buy Value'] != 0:
            v['Cleared'], v['Cleared Percentage'] = calculate_profit(v['Total Buy Value'], v['Total Sell Value'])

        if v['Intraday Buy Value'] != 0:
            v['Intraday Cleared'], v['Intraday Cleared Percentage'] = calculate_profit(v['Intraday Buy Value'], v['Intraday Sell Value'])

    # Prune again
    trades = {k: v for k, v in trades.iteritems() if k == MISC_KEY or trades[k]['Total Quantity'] > 0 or trades[k]['Cleared'] != 0 or trades[k]['Intraday Cleared'] != 0}

    return trades


def update_portfolio(trades, portfolio):
    """ Update portfolio with trades
    """
    print "Updating portfolio..."

    for scrip in trades:
        if scrip == MISC_KEY:
            continue

        portfolio[scrip] = {
                "Total Quantity": trades[scrip]["Total Quantity"],
                "Total Value": trades[scrip]["Total Value"],
                "Average Rate": trades[scrip]["Rate"],
                "Cleared": trades[scrip]["Cleared"],
                "Cleared Percentage": trades[scrip]["Cleared Percentage"],
                "Intraday": trades[scrip]["Intraday Cleared"],
                "Intraday Percentage": trades[scrip]["Intraday Cleared Percentage"],
                "Total Trade Volume": trades[scrip]["Total Trade Volume"],
                "Total Brokerage": trades[scrip]["Total Brokerage"]
                }

    portfolio[MISC_KEY] = {"Total Value": trades[MISC_KEY]["Total Value"]}


def format_report_entry(source, title, value_key, color='blue', title_width=30, value_width=30, change_width=20, old_source=None):
    """ Format a line in report
    """
    entry = ""
    entry += " | {:{width}}: ".format(title, width=title_width)
    value_format = "₹ {:,.2f}"

    if not isinstance(value_key, (list, tuple)):
        value_key = [value_key]

    value = [source[x] for x in value_key]

    if len(value_key) > 1:
        value_format += " ( {:.2f}% )"

    value_entry = value_format.format(*value)

    # Lossy operation
    value = value[0]

    if isinstance(color, (list, tuple)):
        color = color[0] if value < 0 else color[1]

    value_entry = "{:{width}}".format(value_entry, width=value_width)
    color_entry = colored(value_entry, color)
    entry += color_entry

    # Changes
    if old_source and value_key[0] in old_source:
        change = value - old_source[value_key[0]]

        if change != 0:
            change_format = "{:+,.2f}"
            change_color = "red" if change < 0 else "green"

            change_entry = change_format.format(change)

            entry += " | {}".format(colored(change_entry, change_color))

    return entry


def generate_report(transactions):
    """ Create and update the portfolio
    """
    print "Generating portfolio..."

    # Load last report
    try:
        with open('last_report.json') as f:
            last_report = json.load(f)
    except Exception:
        last_report = None

    portfolio = {}

    update_portfolio(trades, portfolio)

    report = process_portfolio(portfolio)

    # Store
    json.dump(report, open('last_report.json', 'w'), indent=2, sort_keys=True)

    final_report = [
            ["A. TOTAL INVESTMENT", 'total', 'white'],
            ["B. CURRENT VALUE", 'current_value', 'yellow'],
            ["C. CHARGES (ACTUAL)", 'charges', 'cyan'],
            ["C1. ANNUAL CHARGES", 'charges_annual', 'cyan'],
            ["C2. LATE PAYMENT CHARGES", 'charges_late', 'cyan'],
            ["C3. CHARGES REFUND", 'charges_credit', 'cyan'],
            ["C4. SERVICE TAX", 'charges_st', 'cyan'],
            ["D. EXIT LOAD (APPROX)", 'exit_load', 'cyan'],
            ["E. PROFIT/LOSS [- EXIT LOAD]", ('profit', 'profit_percentage'), ("red", "green")],
            ["F. CLEARED [- CHARGES]", 'cleared', ("red", "green")],
            ["G. INTRADAY", 'intraday_cleared', ("red", "green")],
            ["H. PREVIOUS BALANCE (ACTUAL)", 'previous_balance', ("red", "green")],
            ["I. DIVIDEND", 'dividend', 'green'],
            ["J. CAPITAL GAIN TAX (APPROX)", 'capital_gain_tax', 'cyan'],
            ["K. BALANCE (F + G + H + I - J)", 'balance', ("red", "green")],
            ["L. TOTAL TRADE VOLUME", 'total_trade_volume', 'blue'],
            ["M. TOTAL BROKERAGE", 'total_brokerage', 'blue'],
            ["N. TOTAL IPO", 'ipo_investment', 'white'],
            ["O. TOTAL FUNDS TRANSFERRED", 'total_funds_transferred', 'white'],
            ["P. SO WHAT IS THE VERDICT??", ('verdict', 'verdict_percentage'), ("red", "green")]
        ]

    # ------------ Display results --------------
    # ------------ Save results to file --------------

    with open('report.txt', 'a') as outfile:
        _saved_stdout = sys.stdout
        sys.stdout = Writer(sys.stdout, outfile)

        print
        print
        print "+" * 80
        print "-" * 30 + " " + colored(datetime.datetime.strftime(datetime.datetime.now(), "%Y-%m-%d %H:%M:%S"), 'cyan') + " " + "-" * 29
        print "+" * 80

        print_tabular(portfolio)

        print "=" * 80

        for report_item in final_report:
            print format_report_entry(report, *report_item, title_width=30, value_width=28, old_source=last_report)

        print "=" * 80

        if report["recommendation"]:
            print "RECOMMENDATIONS:"
            print colored(report["recommendation"][:-1], 'green')
            print "=" * 80

        print
        print "+" * 80
        print

        sys.stdout = _saved_stdout


def process_portfolio(portfolio):
    """ Report from portfolio
    """
    print "Processing portfolio..."

    profit = 0
    total = 0
    current_value = 0
    cleared = 0
    intraday_cleared = 0
    charges = 0
    total_trade_volume = 0
    total_brokerage = 0
    total_dividend = 0
    recommendation = ""

    # Final
    for key in dict(portfolio):
        # Misc
        if key == MISC_KEY:
            charges = portfolio[key]["Total Value"]
            portfolio[key]["Total Value"] = round(portfolio[key]["Total Value"], 2)
        else:
            market_rate = scrip_manager.get_price(key)

            portfolio[key]["Market Rate"] = float(market_rate[0])
            portfolio[key]["Market Change"] = market_rate[1]

            portfolio[key]["Dividend"] = get_dividend(key)

            if portfolio[key]["Total Value"] > 0:
                portfolio[key]["Current Value"] = portfolio[key]["Total Quantity"] * portfolio[key]["Market Rate"]
                portfolio[key]["Profit/Loss"] = portfolio[key]["Current Value"] - portfolio[key]["Total Value"]
                portfolio[key]["Profit/Loss Percentage"] = portfolio[key]["Profit/Loss"] / portfolio[key]["Total Value"] * 100
                portfolio[key]["Average Rate"] = portfolio[key]["Total Value"] / portfolio[key]["Total Quantity"]
            else:
                portfolio[key]["Current Value"] = 0
                portfolio[key]["Profit/Loss"] = 0
                portfolio[key]["Profit/Loss Percentage"] = 0
                portfolio[key]["Average Rate"] = 0

            profit += portfolio[key]["Profit/Loss"]
            total += portfolio[key]["Total Value"]
            current_value += portfolio[key]["Current Value"]
            cleared += portfolio[key]["Cleared"]
            intraday_cleared += portfolio[key]["Intraday"]
            total_trade_volume += portfolio[key]["Total Trade Volume"]
            total_brokerage += portfolio[key]["Total Brokerage"]
            total_dividend += portfolio[key]["Dividend"]

            # Add Profit/Loss Percentage
            portfolio[key]["Profit/Loss"] = (portfolio[key]["Profit/Loss"], portfolio[key]["Profit/Loss Percentage"])

            # Add Cleared Percentage
            portfolio[key]["Cleared"] = (portfolio[key]["Cleared"], portfolio[key]["Cleared Percentage"])

            # Add Intraday Percentage
            portfolio[key]["Intraday"] = (portfolio[key]["Intraday"], portfolio[key]["Intraday Percentage"])

            if portfolio[key]["Profit/Loss Percentage"] > SELL_RECOMMENDATION_CUTOFF:
                sell_price = round(portfolio[key]["Average Rate"] * SELL_RECOMMENDATION_RATE, 2)
                recommendation += "Sell {scrip} at {price}.\n".format(scrip=scrip_manager.get_title_from_scrip(key),
                                                                    price=sell_price)

    # Look at Ledger
    ledger_totals = get_ledger_totals()

    total_transferred = ledger_totals["funds_transferred"] + ipo_investment
    charges_annual = ledger_totals["charges_annual"]
    charges_late = ledger_totals["charges_late"]
    charges_credit = ledger_totals["charges_credit"]
    charges_st = ledger_totals["charges_st"]
    charges += charges_annual
    charges += charges_late
    charges += charges_st
    charges -= charges_credit

    cleared -= charges
    capital_gain_tax = (cleared + intraday_cleared) * CAPITAL_GAIN_TAX_RATE
    exit_load = (current_value * EXIT_LOAD_RATE)
    profit -= exit_load
    previous_balance = PREVIOUS_BALANCE
    balance = previous_balance + cleared + intraday_cleared + total_dividend - capital_gain_tax
    profit_percentage = profit / total * 100
    verdict = balance + profit
    verdict_percentage = verdict / total_transferred * 100

    return {
                "total": total,
                "current_value": current_value,
                "total_funds_transferred": total_transferred,
                "ipo_investment": ipo_investment,
                "exit_load": exit_load,
                "profit": profit,
                "profit_percentage": profit_percentage,
                "capital_gain_tax": capital_gain_tax,
                "cleared": cleared,
                "intraday_cleared": intraday_cleared,
                "previous_balance": previous_balance,
                "dividend": total_dividend,
                "balance": balance,
                "charges": charges,
                "charges_annual": charges_annual,
                "charges_late": charges_late,
                "charges_credit": charges_credit,
                "charges_st": charges_st,
                "total_trade_volume": total_trade_volume,
                "total_brokerage": total_brokerage,
                "verdict": verdict,
                "verdict_percentage": verdict_percentage,
                "recommendation": recommendation
            }


def print_tabular(data):
    """ Display the portfolio in tabular form
    """
    data_table = convert_to_table(data)

    print
    print
    print_table(data_table)
    print
    print


def convert_to_table(data):
    """ Convert dictionary to two-dimentional list
    """
    data_table = []

    keys = [x[3] for x in REPORT_FORMAT]

    data_table.append([x[0] for x in REPORT_FORMAT])

    # Sort the portfolio table
    def sorter(item):
        if item[0] == MISC_KEY:
            return -1

        # No specified sort -> sort by Scrip name
        if not REPORT_ORDER['sort_key']:
            return scrip_manager.get_title_from_scrip(item[0])

        item = item[1]

        sort_key = item[REPORT_ORDER['sort_key']]

        if isinstance(sort_key, (list, tuple)):
            sort_key = sort_key[0]

        if sort_key == 0:
            sort_key = 9999999999 if REPORT_ORDER['blank_at_end'] else -9999999999

            if REPORT_ORDER['reverse']:
                sort_key = -sort_key

        return sort_key

    for key, value in sorted(data.iteritems(), key=sorter, reverse=REPORT_ORDER['reverse']):
        if key == MISC_KEY:
            continue

        row = []
        row.append(scrip_manager.get_title_from_scrip(key))

        row.extend([value[k] for k in keys if k in value])

        data_table.append(row)

    return data_table


def format_table_entry(value, color, width, alignment, is_number=True, is_currency=False):
    """ Format a value in table cell
    """
    if not isinstance(value, (list, tuple)):
        value = [value]

    if not isinstance(color, (list, tuple)):
        color = [color]

    if len(color) > 1:
        color = color[0] if value[0] < 0 else color[1]
    else:
        color = color[0]

    value_entry = ''

    # Zero = blank
    if value[0] == 0:
        value_entry = "_._"
        color = 'grey'
        alignment = '^'
    else:
        if is_currency:
            value_format = "₹ {:,.2f}"
            # Rupee symbol is considered as 3 characters
            width += 2
        else:
            value_format = "{:,.2f}"

        if is_number:
            if len(value) > 1:
                value_format += " ({:.2f}%)"

            value_entry = value_format.format(*value)
        else:
            value_entry = value[0]

    entry = "| " + colored("{0:{alignment}{width}}".format(value_entry, alignment=alignment, width=width), color)

    return entry


def print_table(data_table):
    """ Print the two dimentional list as a table
    """
    for i, entry in enumerate(data_table[0]):
        print "+ {0:-^{width}}".format("", width=REPORT_FORMAT[i][1]),

    print "+"

    is_first = True

    for line in data_table:
        for i, entry in enumerate(line):

            color = REPORT_FORMAT[i][6]
            width = REPORT_FORMAT[i][1]
            alignment = REPORT_FORMAT[i][2]
            is_number = REPORT_FORMAT[i][4]
            is_currency = REPORT_FORMAT[i][5]

            if is_first:
                print "| {0:^{width}}".format(entry, width=width),
            else:
                print format_table_entry(entry, color, width, alignment, is_number, is_currency),

        print "|"

        for i, entry in enumerate(line):
            print "+ {0:-^{width}}".format("", width=REPORT_FORMAT[i][1]),

        print "+"

        is_first = False


def get_dividend(key):
    """ Get dividend earned for scrip
    """
    global dividends

    entries = [x for x in dividends if x['Scrip'] == key]

    return sum(float(item["Total"]) for item in entries)


def get_ledger_totals():
    """ Get the total amounts from Ledger
    """
    ledgers = []
    ledger_totals = {}

    # Parse Ledger files
    for filename in glob.glob('Ledger*.htm*'):
        if filename not in processed_files:
            ledger = parse_ledger_file(filename)
            ledgers.extend(ledger)

    ledger_totals = process_ledger_entries(ledgers)

    return {
            "charges_annual": ledger_totals["Maintenance Charges"],
            "funds_transferred": -(ledger_totals["Transfer"]) - ledger_totals["Withdrawal"],
            "charges_credit": -(ledger_totals["Charges Reversed"]),
            "charges_late": ledger_totals["Late Charges"],
            "charges_st": ledger_totals["Service Tax"]
    }


def parse_ledger_file(filename):
    """ Get data from Ledger file
    """
    print "Processing file: " + filename + "..."
    html = open(filename).read()

    soup = BeautifulSoup(html, 'lxml')

    table = soup.find("table", {"id": "GenTableBy"})

    entries = []

    for row in table.findAll("tr"):
        entry = []

        for cell in row.findAll("td"):
            entry.append("".join(c for c in str(unicode(cell.string).encode('ascii', 'ignore')).strip() if c not in "*[]~"))

        entries.append(entry)

    return entries


def process_ledger_entries(entries):
    """ Process transactions from Ledger
    """
    description_map = {
        "To Bill": "Buy",
        "OPENING BALANCE": "Opening Balance",
        "Direct Credit": "Transfer",
        "Bank Payment": "Withdrawal",
        "By Bill": "Sell",
        "Amc": "Maintenance Charges",
        "Delayed": "Late Charges",
        "Dividend": "Dividend",
        "Reversed": "Charges Reversed",
        "Refunded": "Charges Reversed",
        "Service Tax": "Service Tax"
    }

    totals = {
        "Buy": 0,
        "Opening Balance": 0,
        "Transfer": 0,
        "Withdrawal": 0,
        "Sell": 0,
        "Maintenance Charges": 0,
        "Late Charges": 0,
        "Dividend": 0,
        "Charges Reversed": 0,
        "Service Tax": 0
    }

    for entry in entries:
        scrap_entries = ["Opening Balance"]

        # Scrap unnecessary entries
        if any(item in "".join(entry) for item in scrap_entries):
            continue

        # Clean
        entry = [x.strip() for x in entry]

        item = dict(zip(LEDGER_COLUMNS, entry))

        scrap_keys = LEDGER_COLUMNS[1:4]
        scrap_keys.append(LEDGER_COLUMNS[-1])

        item = {key:value for key,value in item.items() if not any(k in key for k in scrap_keys)}

        item["Description"] = [value for key,value in description_map.items() if key in item["Description"]][0]

        totals[item["Description"]] -= (float(item["Credit"]) if item["Credit"] else 0)
        totals[item["Description"]] += (float(item["Debit"]) if item["Debit"] else 0)

    return totals


if __name__ == '__main__':
    """ Main
    """
    # Setup scrips
    scrip_manager = ScripManager()

    transactions = []
    processed_files = []
    misc_trades = []

    file_list = [
        "__trades.json",
        "__processed.json",
        "__dividends.json",
    ]
    file_data = {}

    # Load data from all files
    for file_name in file_list:
        try:
            file_data[file_name] = json.load(open(file_name))
        except Exception as e:
            print e

    # Load existing transactions
    transactions = file_data["__trades.json"]

    # Load processed file list
    processed_files = file_data["__processed.json"]

    # Load dividend
    dividends = file_data["__dividends.json"]

    for entry in dividends:
        if 'Scrip' not in entry:
            print entry['Security']
            entry['Scrip'] = scrip_manager.get_scrip_from_title(entry['Security'])

    # Parse 'Contract Note' HTML files
    for filename in glob.glob('CN*.htm*'):
        if filename not in processed_files:
            cn_entries = crunch_cn_entries(process_cn_entries(parse_cn_file(filename)))
            transactions.extend(cn_entries)

            processed_files.append(filename)

    # Parse MISC files
    for filename in glob.glob('misc_trades*.json'):
        if filename not in processed_files:
            print "Processing file: " + filename + "..."
            misc_trades = json.load(open(filename))
            transactions.extend(misc_trades)
            processed_files.append(filename)

    # Parse DIVIDENT files
    for filename in glob.glob('dividend*.json'):
        if filename not in processed_files:
            print "Processing file: " + filename + "..."
            dividend = json.load(open(filename))
            dividends.extend(dividend)

            for entry in dividends:
                if 'Scrip' not in entry:
                    entry['Scrip'] = scrip_manager.get_scrip_from_title(entry['Security'])

            processed_files.append(filename)

    # Standardize transactions
    transactions = crunch_transactions(transactions)

    # CAUTION! transactions will be modified by crunch_trades()
    # NOTE! Save
    file_data["__trades.json"] = list(transactions)
    # Start eating them
    trades = crunch_trades(transactions)

    file_data["__dividends.json"] = list(dividends)
    file_data["__processed.json"] = list(processed_files)

    # Save data to all files
    for file_name in file_list:
        try:
            json.dump(file_data[file_name],
                      open(file_name, 'w'),
                      indent=2,
                      sort_keys=True)
        except Exception as e:
            print e

    # Generate the porfolio
    generate_report(trades)
