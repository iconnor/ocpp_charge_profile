""" Read solar output from Fronius inverter """
import requests


def read_power():
    fronius_url = 'http://10.1.1.105:8025/solar_api/v1/GetInverterRealtimeData.cgi?Scope=System'
    r = requests.get(fronius_url)

    stats = r.json()

    current_power = stats.get('Body', {}).get('Data', {}).get('PAC', {}).get('Values', {}).get('1', 0)
    current_power_unit = stats.get('Body', {}).get('Data', {}).get('PAC', {}).get('Unit', '')

    if current_power_unit == 'W':
        print(current_power, current_power_unit)
    else:
        print('Unknown unit', current_power_unit)
    return current_power, current_power_unit