import os

from dotenv import load_dotenv
from flask import Flask, request
import requests

import db_aps
import fb_cache
import fb_templates
import moltin_aps


app = Flask(__name__)

load_dotenv()
FACEBOOK_TOKEN = os.environ['PAGE_ACCESS_TOKEN']
DB = db_aps.get_database_connection()


@app.route('/', methods=['GET'])
def verify():
    '''
    При верификации вебхука у Facebook он отправит запрос на этот адрес. На него нужно ответить VERIFY_TOKEN.
    '''
    if request.args.get('hub.mode') == 'subscribe' and request.args.get('hub.challenge'):
        if not request.args.get('hub.verify_token') == os.environ['VERIFY_TOKEN']:
            return 'Verification token mismatch', 403
        return request.args['hub.challenge'], 200

    return 'Hello world', 200


@app.route('/', methods=['POST'])
def webhook():
    '''
    Основной вебхук, на который будут приходить сообщения от Facebook и Moltin.
    '''
    if request.headers['User-Agent'] == 'moltin/integrations':
        # webhook on moltin products and categories create/update/delete events
        # TODO handle updates and choose cache action
        if request.headers['X-Moltin-Secret-Key'] != os.environ['VERIFY_TOKEN']:
            return 'Verification token mismatch', 403
        fb_cache.update_cached_cards()
        return 'ok', 200

    data = request.get_json()
    if data['object'] == 'page':
        for entry in data['entry']:
            for messaging_event in entry['messaging']:
                postback = None
                sender_id = messaging_event['sender']['id']
                if messaging_event.get('message'):
                    message_text = messaging_event['message']['text']
                if messaging_event.get('postback'):
                    message_text = messaging_event['postback']['title']
                    postback = messaging_event['postback']['payload']
                handle_users_reply(sender_id, message_text, postback)
    return 'ok', 200


def handle_users_reply(sender_id, message_text, postback=None):
    states_functions = {
        'START': handle_start,
        'MENU': handle_menu,
        'CART': handle_cart,
    }
    recorded_state = DB.get(f'fb-{sender_id}')
    if not recorded_state or recorded_state.decode('utf-8') not in states_functions.keys():
        user_state = 'START'
    else:
        user_state = recorded_state.decode('utf-8')
    if message_text == '/start':
        user_state = 'START'
    state_handler = states_functions[user_state]
    next_state = state_handler(sender_id, message_text, postback)
    DB.set(f'fb-{sender_id}', next_state)


def handle_start(recipient_id, message_text, postback):
    send_menu(recipient_id)
    return 'MENU'


def send_menu(recipient_id, category_id=None):
    message_payload = fb_templates.collect_menu_message(recipient_id, category_id)
    send_message(recipient_id, message_payload)


def send_message(recipient_id, message_payload):
    params = {'access_token': FACEBOOK_TOKEN}
    headers = {'Content-Type': 'application/json'}
    request_content = {
        'recipient': {
            'id': recipient_id
        },
        'message': message_payload,
    }

    response = requests.post(
        'https://graph.facebook.com/v7.0/me/messages',
        params=params, headers=headers, json=request_content
    )
    response.raise_for_status()


def handle_menu(recipient_id, message_text, postback):
    if postback in [category['id'] for category in moltin_aps.get_all_categories()]:
        send_menu(recipient_id, postback)
    elif message_text == 'Добавить в корзину':
        add_pizza_to_cart(recipient_id, postback)
    elif message_text == 'Корзина':
        message = fb_templates.collect_cart_message(postback)
        send_message(recipient_id, message)
        return 'CART'
    else:
        send_menu(recipient_id)
    return 'MENU'


def add_pizza_to_cart(recipient_id, product_id):
    quantity = 1
    moltin_aps.add_product_to_cart(f'fb-{recipient_id}', product_id, quantity)
    pizza_name = moltin_aps.get_product_info(product_id)['name']
    message = {'text': f'В корзину добавлена пицца «{pizza_name}»'}
    send_message(recipient_id, message)


def handle_cart(recipient_id, message_text, postback):
    if 'add' in postback:
        pizza_id = postback.split(':')[-1]
        add_pizza_to_cart(recipient_id, pizza_id)
    elif 'remove' in postback:
        item_id = postback.split(':')[-1]
        moltin_aps.remove_item_from_cart(f'fb-{recipient_id}', item_id)
        message = {'text': 'Пицца удалена из корзины'}
        send_message(recipient_id, message)
    else:
        send_menu(recipient_id)
        return 'MENU'
    message = fb_templates.collect_cart_message(f'fb-{recipient_id}')
    send_message(recipient_id, message)
    return 'CART'


def check_db_for_cards():
    keys = DB.keys()
    if b'categories_card' not in keys:
        fb_cache.update_cached_cards()


if __name__ == '__main__':
    check_db_for_cards()
    debug = os.getenv("DEBUG", "false").lower() in ['yes', '1', 'true']
    app.run(debug=debug)
