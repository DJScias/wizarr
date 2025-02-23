import logging
from re import I
import secrets
import string
import os
import requests
import datetime
from flask import request, redirect, render_template, abort, make_response, send_from_directory
from app import app, Invitations, Settings, VERSION
from app.admin import login_required
from plexapi.server import PlexServer
from flask_babel import _
from packaging import version



@app.route('/')
def redirect_to_invite():
    if not Settings.select().where(Settings.key == 'admin_username').exists():
        return redirect('/settings')
    return redirect('/invite')

@app.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(app.root_path, 'static'),
                               'favicon.ico', mimetype='image/vnd.microsoft.icon')

@app.route("/j/<code>", methods=["GET"])
def welcome(code):
    if not Invitations.select().where(Invitations.code == code).exists():
        return render_template('401.html'), 401
    name = Settings.get_or_none(
        Settings.key == "plex_name")
    if name:
        name = name.value
    else:   
        name = "Wizarr"
    resp = make_response(render_template('welcome.html', name=name, code=code))
    resp.set_cookie('code', code)
    return resp


@app.route("/join", methods=["GET", "POST"])
def join():
    if request.method == "POST":
        error = None
        code = request.form.get('code')
        email = request.form.get("email")
        if not Invitations.select().where(Invitations.code == code).exists():
            return render_template("join.html", name=Settings.get(Settings.key == "plex_name").value, code=code, code_error="That invite code does not exist.", email=email)
        if Invitations.select().where(Invitations.code == code, Invitations.used == True, Invitations.unlimited == False).exists():
            return render_template("join.html", name=Settings.get(Settings.key == "plex_name").value, code=code, code_error="That invite code has already been used.", email=email)
        if Invitations.select().where(Invitations.code == code, Invitations.expires <= datetime.datetime.now()).exists():
            return render_template("join.html", name=Settings.get(Settings.key == "plex_name").value, code=code, code_error="That invite code has expired.", email=email)
        try:
            sections = list(
                (Settings.get(Settings.key == "plex_libraries").value).split(", "))
            plex = PlexServer(Settings.get(Settings.key == "plex_url").value, Settings.get(
                Settings.key == "plex_token").value)
            plex.myPlexAccount().inviteFriend(user=email, server=plex, sections=sections)
            logging.info("Invited " + email + " to Plex Server")
            if Invitations.select().where(Invitations.code == code, Invitations.unlimited == 0):
              Invitations.update(used=True, used_at=datetime.datetime.now().strftime(
                  "%Y-%m-%d %H:%M"), used_by=email).where(Invitations.code == code).execute()
            else:
              Invitations.update(used_at=datetime.datetime.now().strftime(
                  "%Y-%m-%d %H:%M"), used_by=email).where(Invitations.code == code).execute()
            return redirect("/setup/accept")
        except Exception as e:
            if 'Unable to find user' in str(e):
                error = _(
                    "That email does not match any Plex account. Please try again.")
                logging.info(
                    "Unable to invite user, cause: no plex account with email: " + email)
            elif "You're already sharing this server" in str(e):
                error = _("This user is already invited to this server.")
                logging.info(
                    "Unable to invite user, cause: plex account already invited with email: " + email)
            elif "The username or email entered appears to be invalid." in str(e):
                error = _("The email entered appears to be invalid.")
                logging.info(
                    "Unable to invite user, cause: email is invalid: " + email)
            else:
                logging.error(str(e))
                error = _(
                    "Something went wrong. Please try again or contact an administrator.")
            return render_template("join.html", name=Settings.get(Settings.key == "plex_name").value, code=code, email_error=error, email=email)
    else:
        code = request.cookies.get('code')
        if code:
            return render_template("join.html", name=Settings.get(Settings.key == "plex_name").value, code=code)
        else:
            return render_template("join.html", name=Settings.get(Settings.key == "plex_name").value)


@app.route('/setup/download', methods=["GET"])
def setup():
    return render_template("setup.html")


def needUpdate():
    try:
        r = requests.get(url="https://raw.githubusercontent.com/Wizarrrr/wizarr/master/.github/latest")
        data = r.content.decode("utf-8")
        if version.parse(VERSION) < version.parse(data):
            return True
        elif version.parse(VERSION) >= version.parse(data):
            return False
        else:
            return False
    except:
        return False


@app.route('/invite', methods=["GET", "POST"])
@login_required
def invite():
    update_msg = False
    if request.method == "POST":
        try:
            code = request.form.get("code").upper()
            if not len(code) == 6:
                return abort(401)
        except:
            code = ''.join(secrets.choice(
                string.ascii_uppercase + string.digits) for _ in range(6))
        if Invitations.get_or_none(code=code):
            return abort(401)  # Already Exists
        expires = None
        unlimited = 0
        if request.form.get("expires") == "day":
            expires = (datetime.datetime.now() +
                       datetime.timedelta(days=1)).strftime("%Y-%m-%d %H:%M")
        if request.form.get("expires") == "week":
            expires = (datetime.datetime.now() +
                       datetime.timedelta(days=7)).strftime("%Y-%m-%d %H:%M")
        if request.form.get("expires") == "month":
            expires = (datetime.datetime.now() +
                       datetime.timedelta(days=30)).strftime("%Y-%m-%d %H:%M")
        if request.form.get("expires") == "never":
            expires = None
        if request.form.get("unlimited"):
            unlimited = 1
        Invitations.create(code=code, used=False, created=datetime.datetime.now(
        ).strftime("%Y-%m-%d %H:%M"), expires=expires, unlimited=unlimited)
        link = os.getenv("APP_URL") + "/j/" + code
        invitations = Invitations.select().order_by(Invitations.created.desc())
        return render_template("invite.html", link=link, invitations=invitations, url=os.getenv("APP_URL"))
    else:
        invitations = Invitations.select().order_by(Invitations.created.desc())
        needUpdate()
        return render_template("invite.html", invitations=invitations, update_msg=update_msg, needUpdate=needUpdate(), url=os.getenv("APP_URL"))


@app.route('/invite/delete=<code>', methods=["GET"])
@login_required
def delete(code):
    Invitations.delete().where(Invitations.code == code).execute()
    return redirect('/invites')


@app.route('/setup/accept', methods=["GET"])
def accept():
    return render_template("accept.html")



@app.route('/setup/requests', methods=["GET"])
def plex_requests():
    if Settings.get_or_none(Settings.key == "overseerr_url"):
        return render_template("requests.html", overseerr_url=Settings.get(Settings.key == "overseerr_url").value)
    else:
        return redirect("/setup/discord")


@app.route('/setup/discord', methods=["GET"])
def plex_discord():
    if Settings.get_or_none(Settings.key == "discord_id"):
        return render_template("discord.html", discord_id=Settings.get(Settings.key == "discord_id").value)
    else:
        return redirect("/setup/tips")

@app.route('/setup/tips')
def tips():
    return render_template("tips.html")


@app.errorhandler(500)
def server_error(e):
    logging.error(e)
    return render_template('500.html'), 500


@app.errorhandler(404)
def server_error(e):
    logging.error(e)
    return render_template('404.html'), 404


@app.errorhandler(401)
def server_error(e):
    logging.error(e)
    return render_template('401.html'), 401

@app.context_processor
def inject_user():
    name = ""
    try:
        name = Settings.get(Settings.key == "plex_name").value
    except:
        name="Wizarr"
        print("Could not find name :( ")
    return dict(header_name=name)