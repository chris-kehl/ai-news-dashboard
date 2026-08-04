import os, sys
sys.path.insert(0, 'scraper')

# Read key directly from .env
av_key = ""
with open('.env') as f:
    for line in f:
        if line.startswith("ALPHA_VANTAGE_API_KEY=*** + 1)
                av_key = v
                break

os.environ['ALPHA_VANTAGE_API_KEY'] = av_key
print("Key loaded, length:", len(av_key))

from tech_analysis_scraper import get_tech_analysis, AV_KEY
print("Module AV_KEY present:", bool(AV_KEY))
print("Env present:", bool(os.getenv('ALPHA_VANTAGE_API_KEY')))
