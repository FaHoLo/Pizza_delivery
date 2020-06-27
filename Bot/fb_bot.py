import os

from dotenv import load_dotenv
from flask import Flask, request
import requests

import db_aps
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
    Основной вебхук, на который будут приходить сообщения от Facebook.
    '''
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
        quantity = 1
        moltin_aps.add_product_to_cart(f'fb-{recipient_id}', postback, quantity)
        pizza_name = moltin_aps.get_product_info(postback)['name']
        message = {'text': f'В корзину добавлена пицца «{pizza_name}»'}
        send_message(recipient_id, message)
    elif message_text == 'Корзина':
        message = fb_templates.collect_cart_message(postback)
        send_message(recipient_id, message)
        return 'MENU'
    else:
        send_menu(recipient_id)
    return 'MENU'


def send_cart(recipient_id, cart_name):
    cart_items = moltin_aps.get_cart_items(cart_name)
    if not cart_items:
        message = {'text': 'Ваша корзина пуста.'}
    else:
        message, state = fb_templates.collect_cart_message(cart_name)
    send_message(recipient_id, message)
    pass


if __name__ == '__main__':
    app.run(debug=True)
