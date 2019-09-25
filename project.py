#!/usr/bin/env python
from flask import Flask, render_template, request
from flask import redirect, jsonify, url_for, flash
from sqlalchemy import create_engine, asc
from sqlalchemy.orm import sessionmaker
from item_catalog_database import Base, Category, Item
from flask import session as login_session
import random
import string
import re
from oauth2client.client import flow_from_clientsecrets
from oauth2client.client import FlowExchangeError
import httplib2
import json
from flask import make_response
import requests

app = Flask(__name__)

CLIENT_ID = json.loads(
    open(
        'client_secret.json',
        'r')
    .read())['web']['client_id']
APPLICATION_NAME = "catalog"

engine = create_engine(
    'sqlite:///categorymenu.db',
    connect_args={'check_same_thread': False})
Base.metadata.bind = engine

DBSession = sessionmaker(bind=engine)
session = DBSession()


@app.route('/fbconnect', methods=['POST'])
def fbconnect():
    if request.args.get('state') != login_session['state']:
        response = make_response(json.dumps('Invalid state parameter.'), 401)
        response.headers['Content-Type'] = 'application/json'
        return response
    access_token = request.data
    print "access token received %s " % access_token
    app_id = json.loads(open('fb_client_secrets.json', 'r').read())[
        'web']['app_id']
    app_secret = json.loads(
        open(
            'fb_client_secrets.json', 'r').read(
                ))['web']['app_secret']
    h = httplib2.Http()
    result = h.request(url, 'GET')[1]

    # Use token to get user info from API
    userinfo_url = "https://graph.facebook.com/v2.8/me"
    '''
        Due to the formatting for the result from the
        server token exchange we have to
        split the token first on commas and select the first index which
        gives us the key : value
        for the server access token then we split it on
        colons to pull out the actual token value and replace the
        remaining quotes with nothing so that it can be used
        directly in the graph api calls
    '''
    token = result.split(',')[0].split(':')[1].replace('"', '')
    h = httplib2.Http()
    result = h.request(url, 'GET')[1]
    # print "url sent for API access:%s"% url
    # print "API JSON result: %s" % result
    data = json.loads(result)
    login_session['provider'] = 'facebook'
    login_session['username'] = data["name"]
    login_session['email'] = data["email"]
    login_session['facebook_id'] = data["id"]

    # The token must be stored in the login_session in order to properly logout
    login_session['access_token'] = token

    # Get user picture
    "url = 'https://graph.facebook.com/v2.8\n"
    "/me/picture?access_token=%s&redirect\n"
    "=0&height=200&width=200' % token"
    h = httplib2.Http()
    result = h.request(url, 'GET')[1]
    data = json.loads(result)

    login_session['picture'] = data["data"]["url"]

    # see if user exists
    user_id = getUserID(login_session['email'])
    if not user_id:
        user_id = createUser(login_session)
    login_session['user_id'] = user_id

    output = ''
    output += '<h1>Welcome, '
    output += login_session['username']

    output += '!</h1>'
    output += '<img src="'
    output += login_session['picture']
    output += ' " style = "width: 300px;height: 300px;border-radius: 150px;"> '

    flash("Now logged in as %s" % login_session['username'])
    return output


@app.route('/gconnect', methods=['POST'])
def gconnect():
    # Validate state token
    if request.args.get('state') != login_session['state']:
        response = make_response(json.dumps(
            'Invalid state parameter.'), 401)
        response.headers['Content-Type'] = 'application/json'
        return response
    # Obtain authorization code
    code = request.data

    try:
        # Upgrade the authorization code into a credentials object
        oauth_flow = flow_from_clientsecrets(
            'client_secrets.json', scope='')
        oauth_flow.redirect_uri = 'postmessage'
        credentials = oauth_flow.step2_exchange(code)
    except FlowExchangeError:
        response = make_response(
            json.dumps(
                'Failed to upgrade the authorization code.'), 401)
        response.headers['Content-Type'] = 'application/json'
        return response

    # Check that the access token is valid.
    access_token = credentials.access_token
    url = ('https://www.googleapis.com/oauth2/v1/tokeninfo?access_token=%s'
           % access_token)
    h = httplib2.Http()
    result = json.loads(h.request(url, 'GET')[1])
    # If there was an error in the access token info, abort.
    if result.get('error') is not None:
        response = make_response(json.dumps(result.get('error')), 500)
        response.headers['Content-Type'] = 'application/json'
        return response

    # Verify that the access token is used for the intended user.
    gplus_id = credentials.id_token['sub']
    if result['user_id'] != gplus_id:
        response = make_response(
            json.dumps("Token's user ID doesn't match given user ID."), 401)
        response.headers['Content-Type'] = 'application/json'
        return response

    # Verify that the access token is valid for this app.
    if result['issued_to'] != CLIENT_ID:
        response = make_response(
            json.dumps("Token's client ID does not match app's."), 401)
        print "Token's client ID does not match app's."
        response.headers['Content-Type'] = 'application/json'
        return response

    stored_access_token = login_session.get('access_token')
    stored_gplus_id = login_session.get('gplus_id')
    if stored_access_token is not None and gplus_id == stored_gplus_id:
        response = make_response(json.dumps(
            'Current user is already connected.'), 200)
        response.headers['Content-Type'] = 'application/json'
        return response

    # Store the access token in the session for later use.
    login_session['access_token'] = credentials.access_token
    login_session['gplus_id'] = gplus_id

    # Get user info
    userinfo_url = "https://www.googleapis.com/oauth2/v1/userinfo"
    params = {'access_token': credentials.access_token, 'alt': 'json'}
    answer = requests.get(userinfo_url, params=params)

    data = answer.json()

    login_session['username'] = data['name']
    login_session['picture'] = data['picture']
    login_session['email'] = data['email']
    # ADD PROVIDER TO LOGIN SESSION
    login_session['provider'] = 'google'

    # see if user exists, if it doesn't make a new one
    user_id = getUserID(data["email"])
    if not user_id:
        user_id = createUser(login_session)
    login_session['user_id'] = user_id

    output = ''
    output += '<h1>Welcome, '
    output += login_session['username']
    output += '!</h1>'
    output += '<img src="'
    output += login_session['picture']
    output += ' " style = "width: 300px; height: 300px;"> '
    flash("you are now logged in as %s" % login_session['username'])
    print "done!"
    return output

# User Helper Functions


def createUser(login_session):
    newUser = User(name=login_session['username'],
                   email=login_session['email'],
                   picture=login_session['picture'])
    session.add(newUser)
    session.commit()
    user = session.query(User).filter_by(email=login_session['email']).one()
    return user.id


def getUserInfo(user_id):
    user = session.query(User).filter_by(id=user_id).one()
    return user


def getUserID(email):
    try:
        user = session.query(User).filter_by(email=email).one()
        return user.id
    except:
        return None

# DISCONNECT - Revoke a current user's token and reset their login_session


@app.route('/gdisconnect')
def gdisconnect():
    # Only disconnect a connected user.
    access_token = login_session.get('access_token')
    if result['status'] == '200':
        response = make_response(
            json.dumps(
                'Successfully disconnected.'), 200)
        response.headers['Content-Type'] = 'application/json'
        return response
    url = 'https://accounts.google.com/o/oauth2/revoke?token=%s' % access_token
    h = httplib2.Http()
    result = h.request(url, 'GET')[0]
    if result['status'] == '200':
        response = make_response(json.dumps('Successfully disconnected.'), 200)
        response.headers['Content-Type'] = 'application/json'
        return response
    else:
        response = make_response(
            json.dumps('Failed to revoke token for given user.', 400))
        response.headers['Content-Type'] = 'application/json'
        return response


@app.route('/')
def categories_print():
    categories = session.query(Category.cat_name).all()
    items = session.query(Category.cat_name, Item.item_name).\
        filter(Item.Category_id == Category.id).all()
    list_length = len(items)
    return render_template(
        'layout.html', categories=categories,
        items=items, list_length=list_length)


@app.route('/login/')
def showLogin():
    state = ''.join(random.choice(string.ascii_uppercase + string.digits)
                    for x in xrange(32))
    login_session['state'] = state
    # return "The current session state is %s" % login_session['state']
    return render_template('login.html', STATE=state)


@app.route('/catalog/<string:category_name>/items')
def specific_category(category_name):
    categories = session.query(Category).\
        filter(category_name == Category.cat_name).all()
    items = session.query(Item).all()
    return render_template(
        'specific_cat.html', category_name=category_name,
        categories=categories, items=items
        )


@app.route('/catalog/<string:category_name>/<string:item_name>')
def show_description(category_name, item_name):
    items = session.query(Item).all()
    return render_template(
        'description.html',
        category_name=category_name,
        item_name=item_name, items=items
        )


@app.route('/loggedIn')
def add_item():
    if 'username' not in login_session:
        return redirect('/login')
    categories = session.query(Category.cat_name).all()
    items = session.query(Category.cat_name, Item.item_name).\
        filter(Item.Category_id == Category.id).all()
    return render_template('add_item.html', categories=categories, items=items)


@app.route('/loggedIn/NewItem', methods=['GET', 'POST'])
def add_item_details():
    if 'username' not in login_session:
        return redirect('/login')
    if request.method == 'POST':
        category1 = request.form['categories_select']
        if not category1 == "#":
            # id of selected category
            real_id = session.query(Category.id).\
                filter(Category.cat_name == category1).one()
            # as integer
            Real_id = convert(real_id)
            NewItem = Item(
                item_name=request.form['item_name'],
                description=request.form['item_description'],
                Category_id=Real_id
                )
            session.add(NewItem)
            flash('New Item %s is added')
            session.commit()
            return redirect(url_for('add_item'))
        else:
            return redirect(url_for('add_item'))
    else:
        return render_template('add_item_details.html')


@app.route('/catalog/<string:category_name>/items/loggedIn')
def specific_category_1(category_name):
    if 'username' not in login_session:
        return redirect('/login')
    categories = session.query(Category).\
        filter(category_name == Category.cat_name).all()
    items = session.query(Item).all()
    return render_template(
        'specific_cat_1.html',
        category_name=category_name, categories=categories, items=items
        )


@app.route('/catalog/<string:category_name>/<string:items_name>/option')
def edit_item(category_name, items_name):
    if 'username' not in login_session:
        return redirect('/login')
    items = session.query(Item).all()
    items_1 = session.query(Item).filter_by(item_name=items_name)
    return render_template(
        'edit.html', category_name=category_name,
        items_name=items_name, items=items, items_1=items_1
        )


@app.route(
    '/catalog/<string:category_name>/<string:item_name>/edit',
    methods=['GET', 'POST']
    )
def edit_item_1(category_name, item_name):
    items = session.query(Item).all()
    categories = session.query(Category).\
        filter(category_name == Category.cat_name).all()
    edited_item = session.query(Item).filter(item_name == Item.item_name).one()
    if 'username' not in login_session:
        return redirect('/login')
    if request.method == 'POST':
        category1 = request.form['categories_select']
        real_id = session.query(Category.id).\
            filter(Category.cat_name == category1).one()
        # id of selected category
        Real_id = convert(real_id)
        # as integer
        if request.form['item_name']:
            edited_item.item_name = request.form['item_name']
        if request.form['item_description']:
            edited_item.description = request.form['item_description']
        if request.form['categories_select']:
            edited_item.Category_id = Real_id
        return redirect(url_for('categories_print'))
    else:
        return render_template(
            'edit_details.html',
            category_name=category_name,
            item_name=item_name, items=items, categories=categories
            )


@app.route(
    '/catalog/<string:category_name>/<string:item_name>/delete',
    methods=['GET', 'POST']
    )
def delete_item(category_name, item_name):
    items = session.query(Item).all()
    categories = session.query(Category).\
        filter(category_name == Category.cat_name).all()
    itemToDelete = session.query(Item).filter_by(item_name=item_name).one()
    if 'username' not in login_session:
        return redirect('/login')
    if request.method == 'POST':
        session.delete(itemToDelete)
        session.commit()
        flash('Item Successfully Deleted')
        return redirect(url_for('categories_print'))
    else:
        return render_template(
            'delete_confirmation.html', name=itemToDelete,
            category_name=category_name, item_name=item_name,
            items=items, categories=categories
            )


@app.route('/catalog/JSON')
def categoriesJSON():
    categories = session.query(Category).all()
    return jsonify(categories=[r.serialize for r in categories])


@app.route('/catalog/<string:category_name_1>/<string:item_name_1>/JSON')
def catalog_item_json(category_name_1, item_name_1):

    item = session.query(Item).filter(Item.item_name == item_name_1,
                                      Category.cat_name ==
                                      category_name_1)\
                                      .first()
    if item is not None:
        return jsonify(item=item.serialize)
    else:
        return jsonify(
            error='item {} does not belong to category {}.'
            .format(item_name_1, category_name_1))


def show_description(category_name, item_name):
    items = session.query(Item).all()
    return render_template(
        'description.html',
        category_name=category_name,
        item_name=item_name, items=items
        )

# a function to convert


def convert(list):
    s = [str(i) for i in list]
    res = int("".join(s))
    return(res)


if __name__ == '__main__':
    app.secret_key = 'super_secret_key'
    app.debug = True
    app.run(host='0.0.0.0', port=8000)
