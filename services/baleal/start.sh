#!/bin/bash

# Start both Python scripts in the background
python3 telegram_bot.py &
python3 instagram_poster.py &

# Wait for all background processes to complete
wait