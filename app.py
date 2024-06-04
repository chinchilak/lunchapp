import streamlit as st
import pandas as pd
import altair as alt
from bs4 import BeautifulSoup
from itertools import product
import datetime
import sqlite3
import requests
import os
import json

CONFIG = "config.json"

class DatabaseConnection:
    def __init__(self, db_name):
        self.db_name = db_name

    def __enter__(self):
        self.conn = sqlite3.connect(self.db_name)
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if exc_type is not None:
            self.conn.rollback()
        else:
            self.conn.commit()
        self.conn.close()

    def cursor(self):
        return self.conn.cursor()

    def execute(self, query, params=()):
        cursor = self.cursor()
        cursor.execute(query, params)
        return cursor

    def fetchall(self, query, params=()):
        with self.cursor() as cur:
            cur.execute(query, params)
            return cur.fetchall()

def load_data():
    if os.path.exists(CONFIG):
        with open(CONFIG, 'r') as file:
            return json.load(file)

def save_data(data):
    with open(CONFIG, 'w') as file:
        json.dump(data, file, indent=4)

def get_restaurant_menu(url:str) -> list:
    response = requests.get(url)
    soup = BeautifulSoup(response.text, 'html.parser')
    menicka_element = soup.find(class_='menicka')
    results_list = []
    if menicka_element:
        div_elements = menicka_element.find_all('div')
        for div in div_elements:
            results_list.append(div.get_text(strip=True))
    return results_list

def store_menus():
    list_all = []
    for nm, url in zip(config["PLACES"], config["URLS"]):
        if "menicka.cz" in url:
            res = get_restaurant_menu(url)
            soup = res[2]
            if res[3] != "":
                res.pop(3)
            res = [item for item in res[2:] if item]
            merged_list = [res[i] + ' ' + res[i+1] for i in range(1, len(res)-1, 2)]
            merged_list.insert(0, soup)
            merged_list.insert(0, nm)
            list_all.append(merged_list)
    return list_all

def date_format():
    now = datetime.datetime.now()
    date = now.strftime("%d. %m. %Y")
    day = now.strftime("%A")
    weekday = {
        'Monday': 'Pondělí',
        'Tuesday': 'Úterý',
        'Wednesday': 'Středa',
        'Thursday': 'Čtvrtek',
        'Friday': 'Pátek',
        'Saturday': 'Sobota',
        'Sunday': 'Neděle'}[day]
    return f"{weekday}, {date}"

def generate_create_table_sql(table_name, column_names):
    columns_str = ", ".join(f"{col} TEXT" for col in column_names)
    sql_query = f"CREATE TABLE IF NOT EXISTS {table_name} ({columns_str})"
    return sql_query

def connect_db():
    with DatabaseConnection(config["DB_NAME"]) as db:
        db.execute(generate_create_table_sql(config["DB_TABLE_VOTES"], config["DB_COLS_VOTES"]))
        db.execute(generate_create_table_sql(config["DB_TABLE_MSGS"], config["DB_COLS_MSGS"]))
        db.execute(generate_create_table_sql(config["DB_TABLE_MENUS"], config["DB_COLS_MENUS"]))

def create_combinations(list1, list2):
    return list(product(list1, list2))

def send_votes(all_combinations, current_date, username, group):
    with DatabaseConnection(config["DB_NAME"]) as db:
        db.execute(f"DELETE FROM {config["DB_TABLE_VOTES"]} WHERE {config["DB_COLS_VOTES"][0]}=? AND {config["DB_COLS_VOTES"][1]}=? AND {config["DB_COLS_VOTES"][2]}=?", (current_date, username, group))
        column_names = ', '.join(config["DB_COLS_VOTES"])
        query = f"INSERT INTO {config["DB_TABLE_VOTES"]} ({column_names}) VALUES (?, ?, ?, ?, ?)"
        for combo in all_combinations:
            db.execute(query, (current_date, username, group, combo[0], combo[1]))

def fetch_votes(current_date, group):
    with DatabaseConnection(config["DB_NAME"]) as db:
        df = pd.read_sql_query(f"SELECT * FROM {config["DB_TABLE_VOTES"]} WHERE {config["DB_COLS_VOTES"][0]} = '{current_date}' AND {config["DB_COLS_VOTES"][2]} = '{group}'", db.conn)
        return df

def send_message(username, group, message):
    c_date = datetime.datetime.now().strftime("%Y-%m-%d")
    c_time = datetime.datetime.now().strftime("%H:%M:%S")
    with DatabaseConnection(config["DB_NAME"]) as db:
        db.execute(f"INSERT INTO {config["DB_TABLE_MSGS"]} ({config["DB_COLS_MSGS"][0]}, {config["DB_COLS_MSGS"][1]}, {config["DB_COLS_MSGS"][2]}, {config["DB_COLS_MSGS"][3]}, {config["DB_COLS_MSGS"][4]}) VALUES (?, ?, ?, ?, ?)", (c_date, c_time, username, group, message))

def fetch_messages(current_date, group):
    with DatabaseConnection(config["DB_NAME"]) as db:
        cursor = db.execute(f"SELECT {config["DB_COLS_MSGS"][1]}, {config["DB_COLS_MSGS"][2]}, {config["DB_COLS_MSGS"][4]} FROM {config["DB_TABLE_MSGS"]} WHERE {config["DB_COLS_MSGS"][0]} = '{current_date}' AND {config["DB_COLS_MSGS"][3]} = '{group}' ORDER BY {config["DB_COLS_MSGS"][1]} DESC")
        return cursor.fetchall()

def transform_data_for_db(inputlist, today):
    transformed_data = []
    for sublist in inputlist:
        category = sublist[0]
        rows = sublist[1:]
        for row in rows:
            transformed_data.append([today, category, row])
    df = pd.DataFrame(transformed_data, columns=config["DB_COLS_MENUS"])
    return df

def get_menus(current_date):
    with DatabaseConnection(config["DB_NAME"]) as db:
        query = f"SELECT * FROM {config["DB_TABLE_MENUS"]} WHERE {config["DB_COLS_MENUS"][0]} = '{current_date}'"
        df = pd.read_sql(query, db.conn)
    grouped = df.groupby(config["DB_COLS_MENUS"][1])
    return grouped


config = load_data()

st.set_page_config(initial_sidebar_state="expanded", layout="wide", page_title="Lunch App")
hide_streamlit_style = """
<style>
# MainMenu {visibility: hidden;}
header {visibility: hidden;}
footer {visibility: hidden;}
</style>
"""
# st.html(hide_streamlit_style)
st.sidebar.html(f"<h2><div style='margin-top: -60px'>Lunch App 1.0</div></h2>")

cols = st.columns([5,0.5,5])

if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if 'username' not in st.session_state:
    st.session_state.username = ""
if 'group' not in st.session_state:
    st.session_state.group = ""

if not st.session_state.logged_in:
    with st.sidebar.form(key='user_form'):
        username = st.text_input("Enter your username")
        group = st.selectbox("Select a group", config["GROUPS"])
        submit_button = st.form_submit_button(label='Submit')

    if submit_button:
        if username and group:
            st.session_state.logged_in = True
            st.session_state.username = username
            st.session_state.group = group
            st.rerun()
        else:
            st.sidebar.error("Please enter your username and select a group.")
else:
    st.sidebar.html(f"<big><b>{st.session_state.username}</b>")
    st.sidebar.html(f"(<i>{st.session_state.group}</i>)</big>")
    logout_button = st.sidebar.button('Logout')

    if logout_button:
        st.session_state.logged_in = False
        st.session_state.username = ""
        st.session_state.group = ""
        st.rerun()

if st.session_state.logged_in:

    if st.session_state.username == "chin":
        with st.sidebar:
            with st.form(key='add_form'):
                st.subheader("Add New Place and URL")
                new_place = st.text_input("New Place")
                new_url = st.text_input("New URL")
                add_button = st.form_submit_button(label="Add")

            with st.form(key='remove_form'):
                st.subheader("Remove Existing Place and URL")
                place_to_remove = st.selectbox("Select Place to Remove", config["PLACES"])
                remove_button = st.form_submit_button(label="Remove")

            if add_button:
                if new_place and new_url:
                    config["PLACES"].append(new_place)
                    config["URLS"].append(new_url)
                    save_data(config)
                    st.success(f"Added: {new_place} - {new_url}")
                else:
                    st.error("Please provide both a place and a URL.")

            if remove_button:
                index_to_remove = config["PLACES"].index(place_to_remove)
                removed_place = config["PLACES"].pop(index_to_remove)
                removed_url = config["URLS"].pop(index_to_remove)
                save_data(config)
                st.success(f"Removed: {removed_place} - {removed_url}")

            groups_to_remove = st.multiselect("Select Groups to Remove", config["GROUPS"])
            new_group = st.text_input("New Group")

            if st.button("Add Group"):
                if new_group and new_group not in config["GROUPS"]:
                    config["GROUPS"].append(new_group)
                    save_data(config)
                    st.success(f"Added: {new_group}")
                elif new_group in config["GROUPS"]:
                    st.warning("Group already exists.")
                else:
                    st.error("Please enter a group name.")

            if st.button("Remove Selected Groups"):
                if groups_to_remove:
                    config["GROUPS"] = [group for group in config["GROUPS"] if group not in groups_to_remove]
                    save_data(config)
                    st.success(f"Removed selected groups: {', '.join(groups_to_remove)}")
                else:
                    st.warning("Please select groups to remove.")


    if not os.path.exists(config["DB_NAME"]):
        connect_db()

    with cols[0]:
        st.html(f"<h4>{date_format()}</h4>")

        cols2 = st.columns([5,5])
        msel_place = cols2[0].multiselect("Select options", config["PLACES"], default=[], key="msel_place")
        msel_time = cols2[1].multiselect("Select options", config["TIMES"], default=[], key="msel_time")

        current_date = (datetime.datetime.now() - datetime.timedelta(days=0)).strftime("%Y-%m-%d")
        username = st.session_state.username
        group = st.session_state.group
        
        if st.button("Vote", use_container_width=True, key="btn_submit"):
            if (msel_place and not msel_time) or (not msel_place and msel_time):
                st.warning("Need to select both categories or leave empty")
            else:
                all_combinations = create_combinations(msel_place, msel_time)
                send_votes(all_combinations, current_date, username, group)
                

        df = fetch_votes(current_date, group)
        

        with st.expander("Votes", expanded=True):
            if not df.empty:
                df_duplicated = df.explode('username')
                df_grouped = df_duplicated.groupby(['place', 'time', 'username']).size().reset_index(name='count')

                chart = alt.Chart(df_grouped).mark_bar(size=40).encode(
                    x=alt.X('time:N', title='', axis=alt.Axis(labelAngle=0)),
                    y=alt.Y('count:Q', title=''),
                    column=alt.Column('place:N', header=alt.Header(title=None)),
                    color=alt.Color('username:N', title="", legend=alt.Legend(orient='top', direction="horizontal", padding=0))
                ).properties(
                    width=alt.Step(80),
                    height=200
                ).configure_axis(
                    grid=False, 
                    domain=False,
                    labelFontSize=16,
                    labelOverlap="greedy"
                ).configure_legend(
                    labelFontSize=16,
                ).configure_header(
                    labelFontSize=16,
                ).configure_view(
                    stroke='darkgrey',
                    strokeWidth=0.5
                ).interactive()

                st.altair_chart(chart, theme="streamlit")
            else:
                st.write("No votes for today")


        st.container(height=20, border=False)
        with st.expander("Chat", expanded=True):
            prompt = st.chat_input("Say something")
            if prompt:
                send_message(username, group, prompt)

            messages = fetch_messages(current_date, group)
            with st.container(height=400):
                for each in messages:
                    st.html(f"<i>{each[0]}</i>&nbsp;&nbsp;<b>{each[1]}</b>:&nbsp;&nbsp;{each[2]}")

    with cols[1]:
        if st.button("Refresh page"):
            st.rerun()


    with cols[2]:
        with DatabaseConnection(config["DB_NAME"]) as db:
            if st.button("Refresh menus"):
                lst = store_menus()
                mdf = transform_data_for_db(lst, current_date)
                mdf.to_sql(config["DB_TABLE_MENUS"], db.conn, if_exists="replace", index=False)
                menus = get_menus(current_date)
            else:
                menus = get_menus(current_date)


        for category, group in menus:
            with st.expander(f":grey[{category}]", expanded=False):
                for _, row in group.iterrows():
                    st.write(row[config["DB_COLS_MENUS"][2]])
else:
    st.write("Please log in using the form in the sidebar.")
