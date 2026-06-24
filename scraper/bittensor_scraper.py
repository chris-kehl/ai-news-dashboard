#!/usr/bin/env python3
from taostats import get_bittensor_data

def get_bittensor_intelligence():
    return get_bittensor_data()

if __name__ == '__main__':
    import json
    print(json.dumps(get_bittensor_intelligence(), indent=2))
