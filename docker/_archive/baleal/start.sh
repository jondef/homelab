#!/bin/bash

# Start both Python scripts in the background
python3 telegram_bot.py &

# Wait for all background processes to complete
wait