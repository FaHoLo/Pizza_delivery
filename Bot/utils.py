from geopy.distance import distance
import requests

import moltin_aps


def fetch_coordinates(apikey, place):
    base_url = 'https://geocode-maps.yandex.ru/1.x'
    params = {'geocode': place, 'apikey': apikey, 'format': 'json'}
    response = requests.get(base_url, params=params)
    response.raise_for_status()
    places_found = response.json()['response']['GeoObjectCollection']['featureMember']
    if not places_found:
        return None, None
    most_relevant = places_found[0]
    lon, lat = most_relevant['GeoObject']['Point']['pos'].split(' ')
    return float(lat), float(lon)


def get_nearest_pizzeria(customer_coords):
    pizzerias = moltin_aps.get_all_entries('pizzeria')
    for pizzeria in pizzerias:
        pizzeria_coords = (pizzeria['latitude'], pizzeria['longitude'])
        pizzeria['distance'] = distance(customer_coords, pizzeria_coords).kilometers
    nearest_pizzeria = min(pizzerias, key=get_pizzeria_distance)
    return nearest_pizzeria


def get_pizzeria_distance(pizzeria):
    return pizzeria['distance']
