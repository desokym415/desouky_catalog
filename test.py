#!/usr/bin/env python
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from item_catalog_database import Category, Base, Item
 
engine = create_engine('sqlite:///categorymenu.db')

Base.metadata.bind = engine
 
DBSession = sessionmaker(bind=engine)
session = DBSession()

categories = session.query(Category).all()
for cat in categories:
    print cat.cat_name
    print cat.id

items = session.query(Item).all()
for itemaia in items:
    print itemaia.item_name
    print itemaia.id
    