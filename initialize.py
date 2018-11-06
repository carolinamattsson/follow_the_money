'''
Initialize a payment processing system

Up-to-date code: https://github.com/Carromattsson/follow_the_money
Copyright (C) 2018 Carolina Mattsson, Northeastern University
'''

from collections import defaultdict
from datetime import datetime, timedelta
import math

class System():
    # A payment system, here, is little more than a dictionary of accounts that keeps track of its boundaries
    def __init__(self,transaction_header,timeformat,timewindow):
        self.accounts = {}
        self.txn_header = [term.replace("rev","fee") if "rev" in term else term for term in transaction_header]
        self.timeformat = timeformat
        self.timewindow = (datetime.strptime(timewindow[0],self.timeformat),datetime.strptime(timewindow[1],self.timeformat))
        self.boundary_type = None
        self.get_txn_categ = lambda txn: "transfer"
        self.fee_convention = None
        self.get_amounts = lambda txn: (txn.amt,txn.amt,0)
        self.balance_type = None
        self.needs_balances = lambda txn: (max(txn.src.balance,txn.amt_out),max(txn.tgt.balance,-txn.amt_in))
    def define_fee_accounting(self,fee_convention,new_txn_header=None):
        self.fee_convention = fee_convention
        if new_txn_header: self.txn_header = new_txn_header
        if   fee_convention == "sender":
            self.get_amounts = lambda txn: (txn.amt+txn.src_fee,txn.amt,txn.src_fee)
        elif fee_convention == "recipient":
            self.get_amounts = lambda txn: (txn.amt,txn.amt-txn.tgt_fee,txn.tgt_fee)
        elif fee_convention == "split":
            self.get_amounts = lambda txn: (txn.amt+txn.src_fee,txn.amt-txn.tgt_fee,txn.src_fee+txn.tgt_fee)
    def define_boundary(self,boundary_type,transaction_categories=None,account_categories=None,category_order=None,category_follow=None):
        self.boundary_type = boundary_type
        if   boundary_type == "transactions":
            self.txn_categs = defaultdict(lambda:"system",transaction_categories)
            self.get_txn_categ = lambda txn: self.txn_categs[txn.type]
        elif boundary_type == "accounts":
            self.categ_follow = set(category_follow)
            self.get_txn_categ = lambda txn: self.get_txn_categ_accts(txn.src_categ,txn.tgt_categ)
        elif boundary_type == "inferred_accounts":
            self.acct_categs = account_categories
            self.categ_order = category_order
            self.categ_follow = set(category_follow)
            self.get_txn_categ = lambda txn: self.get_txn_categ_accts(txn.src.categ,txn.tgt.categ)
        elif boundary_type == "accounts+otc":
            self.categ_follow = set(category_follow)
            self.txn_categs = defaultdict(lambda:"system",transaction_categories)
            self.get_txn_categ = lambda txn: self.get_txn_categ_accts_otc(txn.src_categ,txn.tgt_categ,txn)
        elif boundary_type == "inferred_accounts+otc":
            self.acct_categs = account_categories
            self.categ_order = category_order
            self.categ_follow = set(category_follow)
            self.txn_categs = defaultdict(lambda:"system",transaction_categories)
            self.get_txn_categ = lambda txn: self.get_txn_categ_accts_otc(txn.src.categ,txn.tgt.categ,txn)
    def define_needs_balances(self,balance_type):
        self.balance_type = balance_type
        if balance_type == "pre":
            self.needs_balances = lambda txn: (float(txn.src_balance),float(txn.tgt_balance))
        elif balance_type == "post":
            self.needs_balances = lambda txn: (float(txn.src_balance)+txn.amt_out,float(txn.tgt_balance)-txn.amt_in)
    def has_account(self,acct_ID):
        return acct_ID in self.accounts
    def get_account(self,acct_ID):
        return self.accounts[acct_ID]
    def create_account(self,acct_ID):
        self.accounts[acct_ID] = Account(acct_ID)
        return self.accounts[acct_ID]
    def reset(self,no_balance=False,Tracker=None):
        for acct_ID,acct in self.accounts.items():
            acct.reset(no_balance,Tracker)
        return self
    def get_txn_categ_accts(self,src_categ,tgt_categ):
        # this method determines whether a transaction is a 'deposit', 'transfer', or 'withdraw' in cases where accounts are either provider-facing or public-facing, and only the latter reflect "real" use of the ecosystem
        # the determination is based on whether the source and target are on the public-facing or provider-facing side of the ecosystem
        src_follow = src_categ in self.categ_follow
        tgt_follow = tgt_categ in self.categ_follow
        if     src_follow and     tgt_follow: return 'transfer'
        if not src_follow and     tgt_follow: return 'deposit'
        if     src_follow and not tgt_follow: return 'withdraw'
        if not src_follow and not tgt_follow: return 'system'
    def get_txn_categ_accts_otc(self,src_categ,tgt_categ,txn):
        # this method determines whether a transaction is a 'deposit', 'transfer', or 'withdraw' in cases where accounts are either provider-facing or public-facing, and only the latter reflect "real" use of the ecosystem
        # the determination is based on whether the source and target are on the public-facing or provider-facing side of the ecosystem
        src_follow = src_categ in self.categ_follow
        tgt_follow = tgt_categ in self.categ_follow
        if     src_follow and     tgt_follow: return 'transfer'
        if not src_follow and     tgt_follow: return 'deposit'
        if     src_follow and not tgt_follow: return 'withdraw'
        if not src_follow and not tgt_follow:
            txn_type = txn.type
            txn.type = "OTC_"+txn.type
            return self.txn_categs[txn_type]
    def process(self,txn):
        # adjust account balances accordingly
        txn.src.balance = txn.src.balance-txn.amt_out
        txn.tgt.balance = txn.tgt.balance+txn.amt_in

class Transaction(object):
    # A transaction, here, contains the basic features of a transaction with references to the source and target accounts
    def __init__(self, src, tgt, txn_dict):
        # reference the accounts the transaction moves between
        self.src = src
        self.tgt = tgt
        # make the transaction attributes object properties
        for key, value in txn_dict.items():
            setattr(self, key, value)
        # use the fee convention to determine how much is leaving the souce account, entering the target account, and disappearing in between
        self.amt_out,self.amt_in,self.fee = self.system.get_amounts(self)
        if self.amt_out < self.amt_in: raise ValueError("Invalid transaction (amount sent < amount received): ",str(txn_dict))
        try:
            self.fee_scaling = self.fee/self.amt_in
        except:
            self.fee_scaling = None
        try:
            self.type
        except:
            self.type = "-".join([self.src_categ,self.tgt_categ])
    def __str__(self):
        return ",".join(str(self.__dict__[term]) for term in self.system.txn_header)
    def to_print(self):
        return(str(self).split(','))
    @classmethod
    def create(cls,src,tgt,txn_dict,get_categ):
        # This method creates a Transaction object from a dictionary and object references to the source and target accounts
        # The dictionary here is read in from the file, and has System.txn_header as the keys
        txn_dict['timestamp'] = datetime.strptime(txn_dict['timestamp'],cls.system.timeformat)
        for term in ['amt','fee','src_fee','tgt_fee']:
            try:
                txn_dict[term] = float(txn_dict[term])
            except:
                continue
        txn = cls(src,tgt,txn_dict)
        if get_categ: txn.categ = cls.system.get_txn_categ(txn)
        return txn

class Account(dict):
    # An account, here, contains the most important features of accounts and can contain tracking mechanisms
    def __init__(self, acct_ID):
        self.acct_ID  = acct_ID
        self.starting_balance = 0
        self.balance = 0
        self.categs = set()
        self.categ = None
        self.tracked = False
        self.tracker = None
    def close_out(self):
        self.balance = 0
        self.tracker = None
    def reset(self,no_balance,Tracker):
        if no_balance: self.starting_balance = 0
        self.balance = self.starting_balance
        self.tracked = False
        if Tracker:
            self.track(Tracker)
        else:
            self.tracker = None
    def update_categ(self, src_tgt, txn_type):
        # this collects the categories of account holder we've seen this user be
        if txn_type in self.system.acct_categs:
            self.categs.add(self.system.acct_categs[txn_type][src_tgt])
    def has_tracker(self):
        return isinstance(self.tracker,list)
    def track(self,Tracker_Class):
        self.tracker = Tracker_Class(self)
    def infer_balance(self, amt):
        # this function upps the running balance in the account, also adjusting the inferred starting balance
        self.starting_balance += amt
        self.balance += amt
    def remove_balance(self, amt):
        # this function drops the running balance in the account, also adjusting the inferred starting balance
        self.balance -= amt
    def adjust_balance_up(self, missing):
        if self.has_tracker(): self.tracker.adjust_tracker_up(missing)
        self.infer_balance(missing)
    def adjust_balance_down(self, extra):
        if self.has_tracker(): yield from self.tracker.adjust_tracker_down(extra)
        self.remove_balance(extra)

def setup_system(config_data):
    ############### Parse config file ##################
    transaction_header = config_data["transaction_header"]
    timeformat = config_data["timeformat"]
    timewindow = (config_data["timewindow_beg"],config_data["timewindow_end"])
    ############### Initialize system ##################
    system = System(transaction_header,timeformat,timewindow)
    ############ Make Classes System-aware #############
    Transaction.system = system
    Account.system = system
    return system

def define_fee_accounting(system,config_data):
    fee_convention = config_data["revenue/fee"]
    if   fee_convention == "sender":
        new_txn_header = None if "src_fee" in system.txn_header else ["src_"+term if term == "fee" else term for term in system.txn_header]
        system.define_fee_accounting("sender",new_txn_header)
    elif fee_convention == "recipient":
        new_txn_header = None if "tgt_fee" in system.txn_header else ["tgt_"+term if term == "fee" else term for term in system.txn_header]
        system.define_fee_accounting("recipient",new_txn_header)
    elif fee_convention == "split":
        system.define_fee_accounting("split")
    else:
        raise ValueError("Config error: 'revenue/fee' options are 'sender', 'recipient', 'split' -- ",fee_convention)
    return system

def define_system_boundary(system,config_data):
    boundary_type = config_data["boundary_type"]
    if   boundary_type == 'transactions':
        system.define_boundary('transactions',transaction_categories=config_data["transaction_categories"])
    elif boundary_type == 'accounts':
        system.define_boundary('accounts',category_follow=config_data["account_following"])
    elif boundary_type == 'inferred_accounts':
        system.define_boundary('inferred_accounts',category_follow=config_data["account_following"],account_categories=config_data["account_categories"],category_order=config_data["account_order"])
    elif boundary_type == 'accounts+otc':
        system.define_boundary('accounts+otc',category_follow=config_data["account_following"],transaction_categories=config_data["transaction_categories"])
    elif boundary_type == 'inferred_accounts+otc':
        system.define_boundary('inferred_accounts+otc',category_follow=config_data["account_following"],account_categories=config_data["account_categories"],category_order=config_data["account_order"],transaction_categories=config_data["transaction_categories"])
    else:
        raise ValueError("Config error: 'boundary_type' options are 'transactions', 'accounts', 'inferred_accounts', 'accounts+otc', 'inferred_accounts+otc' -- ",boundary_type)
    return system

def load_accounts(accounts_file):
    return accounts

def initialize_transactions(txn_reader,system,report_file,get_categ=False):
    import traceback
    # Initialize the transaction. There are two steps:
    #                               1) Ensure the source and target accounts exist
    #                               3) Create the transaction object
    for txn in txn_reader:
        try:
            # define the transaction, creating accounts and trackers if needed
            src = system.get_account(txn['src_ID']) if system.has_account(txn['src_ID']) else system.create_account(txn['src_ID'])
            tgt = system.get_account(txn['tgt_ID']) if system.has_account(txn['tgt_ID']) else system.create_account(txn['tgt_ID'])
            yield Transaction.create(src,tgt,txn,get_categ)
        except:
            report_file.write("ISSUE W/ INITIALIZING: "+str(txn)+"\n"+traceback.format_exc()+"\n")

def infer_account_categories(system,transaction_file,report_filename):
    import csv
    with open(transaction_file,'r') as txn_file, open(report_filename,'w') as report_file:
        txn_reader = csv.DictReader(txn_file,system.txn_header,delimiter=",",quotechar="'",escapechar="%")
        transactions = initialize_transactions(txn_reader,system,report_file)
        for txn in transactions:
            txn.src.update_categ('src',txn.type)
            txn.tgt.update_categ('tgt',txn.type)
    for acct_ID,account in system.accounts.items():
        for categ in system.categ_order:
            if categ in account.categs:
                account.categ = categ
                break
    return system

def infer_starting_balance(system,transaction_file,report_filename):
    import csv
    with open(transaction_file,'r') as txn_file, open(report_filename,'a') as report_file:
        txn_reader = csv.DictReader(txn_file,system.txn_header,delimiter=",",quotechar="'",escapechar="%")
        transactions = initialize_transactions(txn_reader,system,report_file)
        for txn in transactions:
            src_balance, tgt_balance = txn.system.needs_balances(txn)
            if src_balance > txn.src.balance: txn.src.infer_balance(src_balance - txn.src.balance)
            if tgt_balance > txn.tgt.balance: txn.tgt.infer_balance(tgt_balance - txn.tgt.balance)
            txn.system.process(txn)
    return system

def discover_account_categories(src,tgt,amt,basics=None,txn_type=None):
    if not txn_type: txn_type = ''
    src.categs.add('src~'+txn_type)
    tgt.categs.add('tgt~'+txn_type)
    # update the account basics
    if basics:
        src.basics.setdefault(txn_type,{'txns_in':0,'txns_out':0,'amt_in':0,'amt_out':0,'fee':0,'alters_in':set(),'alters_out':set()})
        tgt.basics.setdefault(txn_type,{'txns_in':0,'txns_out':0,'amt_in':0,'amt_out':0,'fee':0,'alters_in':set(),'alters_out':set()})
        src.basics[txn_type]['txns_out'] += 1
        src.basics[txn_type]['amt_out']  += float(amt)
        src.basics[txn_type]['fee']      += float(fee)
        src.basics[txn_type]['alters_out'].add(tgt.acct_ID)
        tgt.basics[txn_type]['txns_in']  += 1
        tgt.basics[txn_type]['amt_in']   += float(amt)
        tgt.basics[txn_type]['alters_in'].add(src.acct_ID)
    return src, tgt

def start_report(report_filename,args):
    import os
    with open(report_filename,'w') as report_file:
        report_file.write("Initialing 'follow the money' for: "+os.path.abspath(args.input_file)+"\n")
        report_file.write("Using the configuration file: "+os.path.abspath(args.config_file)+"\n")
        if args.no_balance: report_file.write("    Ignoring inferred starting balances (no effect if balances are given)."+"\n")
        report_file.write("\n\n")
        report_file.flush()

if __name__ == '__main__':
    print("Please run main.py, this file keeps classes and functions.")
