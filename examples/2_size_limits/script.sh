#!/bin/bash

# Limiting the size of tracked flows
python3 ../../follow_the_money.py account_txns.csv account_config.json output --prefix size_ --lifo --mixed --smallest 5
