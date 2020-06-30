import logging
import os

import requests
from slugify import slugify

import moltin_requests


moltin_logger = logging.getLogger('moltin_loger')

APP_JSON_HEADER = {'Content-Type': 'application/json'}


def get_all_categories(sort=None):
    method = f'categories?{sort}'
    categories = moltin_requests.make_get_request(method)
    return categories


def get_products_by_category_id(category_id, sort=None):
    method = f'products?filter=eq(category.id,{category_id})&{sort}'
    products = moltin_requests.make_get_request(method)
    return products


def update_entry(entry_values, flow_slug, entry_id):
    method = f'flows/{flow_slug}/entries/{entry_id}'
    payload = {'data': {'id': entry_id, 'type': 'entry'}}
    payload['data'].update(entry_values)
    updated_entry_info = moltin_requests.make_put_request(method, payload=payload)
    return updated_entry_info


def get_entry(flow_slug, entry_id):
    method = f'flows/{flow_slug}/entries/{entry_id}'
    entry_info = moltin_requests.make_get_request(method)
    return entry_info


def get_all_entries(flow_slug):
    method = f'flows/{flow_slug}/entries'
    entries = moltin_requests.make_get_request(method)
    return entries


def create_flow(flow_info, enabled=True):
    '''
    flow_info = {
        'name': 'Flow name',
        'description': 'Flow description',
    }
    '''
    method = 'flows'
    flow_info.update({
        'slug': slugify(flow_info['name']),
        'enabled': enabled,
    })
    payload = {'data': {'type': 'flow'}}
    payload['data'].update(flow_info)
    flow_info = moltin_requests.make_post_request(method, APP_JSON_HEADER, payload=payload)['data']
    return flow_info


def create_field(flow_id, name, description, field_type, required=False, unique=False, default=None, enabled=True, omit_null=False):
    '''
    Field types: 'string', 'integer', 'boolean', 'float', 'date', 'relationship'
    '''
    method = 'fields'
    slug = slugify(name)
    payload = {'data': {
        'type': 'field',
        'name': name,
        'slug': slug,
        'description': description,
        'field_type': field_type,
        'required': required,
        'unique': unique,
        'enabled': enabled,
        'omit_null': omit_null,
        'relationships': {
            'flow': {
                'data': {
                    'type': 'flow',
                    'id': flow_id,
                }
            }
        }
    }}
    if not unique and default:
        payload['data']['default'] = default
    field_info = moltin_requests.make_post_request(method, APP_JSON_HEADER, payload=payload)['data']
    return field_info


def add_field_entry(entry_values, flow_slug):
    '''
    entry_values = {
        'entry-1-slug': 'entry_1_value',
        'entry-2-slug': 'entry_2_value',
        ...
    }
    '''
    method = f'flows/{flow_slug}/entries'
    payload = {'data': {'type': 'entry'}}
    payload['data'].update(entry_values)
    entry_info = moltin_requests.make_post_request(method, APP_JSON_HEADER, payload=payload)['data']
    return entry_info


def create_product_and_add_image(product_id, product_name, description, img_url, price, currency='RUB'):
    sku = str(product_id)
    slugged_name = slugify(product_name)
    slug = f'{slugged_name}-{sku}'
    pizza_info = {
        'name': product_name,
        'sku': sku,
        'slug': slug,
        'description': description,
        'manage_stock': False,
        'price': [{
            'amount': price,
            'currency': currency,
            'includes_tax': True
        }],
        'status': 'live',
        'commodity_type': 'physical',
    }
    product_id = create_product(pizza_info)['id']
    image_path = download_image(img_url)
    try:
        image_id = create_file(image_path, 'true')['id']
        add_product_main_image(product_id, image_id)
    finally:
        os.remove(image_path)


def download_image(url, folder='images'):
    response = requests.get(url)
    response.raise_for_status()
    image_name = url.split('/')[-1]
    os.makedirs(folder, exist_ok=True)
    image_path = os.path.join(folder, image_name)
    with open(image_path, 'wb') as new_file:
        new_file.write(response.content)
    return image_path


def create_product(product_info):
    method = 'products'
    payload = {'data': {'type': 'product'}}
    payload['data'].update(product_info)
    product_info = moltin_requests.make_post_request(method, method_headers=APP_JSON_HEADER, payload=payload)['data']
    moltin_logger.debug('Product created')
    return product_info


def create_file(filepath, public_status):
    method = 'files'
    files = {
        'file': (filepath, open(filepath, 'rb')),
        'public': (None, public_status),
    }
    file_info = moltin_requests.make_post_request(method, files=files)['data']
    moltin_logger.debug('File created')
    return file_info


def add_product_main_image(product_id, image_id):
    method = f'products/{product_id}/relationships/main-image'
    payload = {'data': {
        'type': "main_image",
        'id': image_id,
    }}
    response = moltin_requests.make_post_request(method, method_headers=APP_JSON_HEADER, payload=payload)
    moltin_logger.debug('Main image was added')
    return response


def get_all_products():
    method = 'products'
    # TODO Paginaton
    products = moltin_requests.make_get_request(method)
    moltin_logger.debug('Got all products')
    return products


def get_product_info(product_id):
    method = f'products/{product_id}'
    product_info = moltin_requests.make_get_request(method)
    moltin_logger.debug(f'Got product «{product_id}» info')
    return product_info


def get_file_info(file_id):
    method = f'files/{file_id}'
    file_info = moltin_requests.make_get_request(method)
    moltin_logger.debug(f'Got file «{file_id}» info')
    return file_info


def create_customer(customer_info):
    payload = {'data': {'type': 'customer'}}
    payload['data'].update(customer_info)
    method = 'customers'
    response = moltin_requests.make_post_request(method, method_headers=APP_JSON_HEADER, payload=payload)
    moltin_logger.debug('Customer created')
    return response


def update_customer_info(customer_id, customer_info):
    payload = {'data': {'type': 'customer'}}
    payload['data'].update(customer_info)
    method = f'customers/{customer_id}'
    response = moltin_requests.make_put_request(method, payload)
    moltin_logger.debug('Customer info updated')
    return response


def get_cart(cart_name):
    method = f'carts/{cart_name}'
    cart = moltin_requests.make_get_request(method)
    moltin_logger.debug(f'Got «{cart_name}» cart')
    return cart


def get_cart_items(cart_name):
    method = f'carts/{cart_name}/items'
    cart_items = moltin_requests.make_get_request(method)
    moltin_logger.debug(f'Got cart «{cart_name}» items')
    return cart_items


def add_product_to_cart(cart_name, product_id, quantity):
    method = f'carts/{cart_name}/items'
    payload = {
        'data': {
            'id': product_id,
            'type': 'cart_item',
            'quantity': quantity,

        }
    }
    moltin_requests.make_post_request(method, method_headers=APP_JSON_HEADER, payload=payload)
    moltin_logger.debug(f'Product was added to «{cart_name}» cart')


def remove_item_from_cart(cart_name, item_id):
    method = f'carts/{cart_name}/items/{item_id}'
    response = moltin_requests.make_delete_request(method).json()
    moltin_logger.debug(f'Item {item_id} was deleted from cart')
    return response


def delete_cart(cart_name):
    method = f'carts/{cart_name}'
    response = moltin_requests.make_delete_request(method)
    moltin_logger.debug(f'Cart «{cart_name}» was deleted. Response code is: {response.status_code}')
    return response.status_code == 204
