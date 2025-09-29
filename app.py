from flask import Flask, render_template, request, redirect, session
import sqlite3 as sq
import json, time, os, io, sys

def database():
    conn = sq.connect("database.db")
    curr = conn.cursor()

    curr.execute(
        """
        create table if not exists account(
                 id integer primary key autoincrement,
                 name text,
                 username text unique,
                 email text,
                 password text
                 )
    """
    )
    curr.execute(
        """
        create table if not exists user_progress(
            id integer primary key autoincrement,
            user_id integer not null,
            levels_cleared integer default 0,
            coins integer default 0,
            output_levels_cleared integer default 0,
            output_coins integer default 0,
            write_levels_cleared integer default 0,
            write_coins integer default 0,
            quiz_levels_cleared integer default 0,
            quiz_coins integer default 0,
            foreign key(user_id) references account(id)
        )
    """
    )
    conn.commit()
    conn.close()


DATA_FILE = os.path.join("data", "spot-the-error-levels.json")


def load_levels():
    with open(DATA_FILE, "r") as f:
        return json.load(f)


levels = load_levels()

OUTPUT_FILE = os.path.join("data", "output.json")


def load_output_levels():
    with open(OUTPUT_FILE, "r") as f:
        return json.load(f)["levels"]


output_levels = load_output_levels()

QUIZ_FILE = os.path.join("data", "quiz.json")


def load_quiz_levels():
    with open(QUIZ_FILE, "r") as f:
        return json.load(f)["levels"]


quiz_levels = load_quiz_levels()

app = Flask(__name__)
app.secret_key = "Hello"


@app.route("/")
def landing():
    return render_template("index.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form["name"]
        username = request.form["username"]
        email = request.form["email"]
        password = request.form["password"]

        conn = sq.connect("database.db")
        curr = conn.cursor()

        curr.execute(
            " insert into account(name, username, email, password) values (?, ?, ?, ?) ",
            (name, username, email, password),
        )

        conn.commit()
        conn.close()

        return redirect("/login")
    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    message = None
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        conn = sq.connect("database.db")
        cur = conn.cursor()

        cur.execute(
            "select * from account where username = ? and password = ?",
            (username, password),
        )
        user = cur.fetchone()
        cur.execute("select name from account where username = ?", (username,))
        actual_name = cur.fetchone()
        if actual_name:
            name = actual_name[0]
            session["p_name"] = name

        if user:
            return redirect("/home")
        else:
            message = "Invalid Credentials!"

    return render_template("login.html", message=message)


@app.route("/logout")
def logout():
    return render_template("login.html")


@app.route("/home")
def home():
    return render_template("home.html", name=session["p_name"])


@app.route("/spoterror", methods=["GET", "POST"])
def spot_error():
    name = session["p_name"]
    conn = sq.connect("database.db")
    conn.row_factory = sq.Row
    cur = conn.cursor()

    cur.execute("SELECT id FROM account WHERE name = ?", (name,))
    user_row = cur.fetchone()
    user_id = user_row["id"]

    cur.execute("SELECT * FROM user_progress WHERE user_id = ?", (user_id,))
    progress = cur.fetchone()

    if not progress:
        cur.execute(
            "INSERT INTO user_progress(user_id, levels_cleared, coins) VALUES (?, ?, ?)",
            (user_id, 0, 0),
        )
        conn.commit()
        levels_cleared = 0
        coins = 0
    else:
        levels_cleared = progress["levels_cleared"]
        coins = progress["coins"]

    if levels_cleared == len(levels):
        conn.close()
        return render_template("completed.html", coins=coins, name=name)

    level_data = levels[levels_cleared]
    message = None

    if request.method == "POST":
        try:
            line_number = int(request.form["line_number"])
            corrected_line = request.form["corrected_line"]
            lines = level_data["buggy_code"].split("\n")
            if 1 <= line_number <= len(lines):
                lines[line_number - 1] = corrected_line
                user_code = "\n".join(lines)
                local_env = {}
                try:
                    exec(user_code, {}, local_env)

                    levels_cleared += 1
                    coins += 999
                    cur.execute(
                        "UPDATE user_progress SET levels_cleared=?, coins=? WHERE user_id=?",
                        (levels_cleared, coins, user_id),
                    )
                    conn.commit()

                    if levels_cleared == len(levels):
                        conn.close()
                        return render_template("completed.html", coins=coins, name=name)
                    else:
                        level_data = levels[levels_cleared]
                        message = "✅ Correct! Level Up!"
                except Exception as e:
                    message = f"❌ Error: {str(e)}. Try again!"
            else:
                message = "⚠️ Invalid line number."
        except ValueError:
            message = "⚠️ Please enter a valid number."

    conn.close()
    return render_template(
        "spoterror.html", level_data=level_data, message=message, name=name, coins=coins
    )


@app.route("/outputchallenge", methods=["GET", "POST"])
def output_challenge():
    name = session["p_name"]
    conn = sq.connect("database.db")
    conn.row_factory = sq.Row
    cur = conn.cursor()

    # find user
    cur.execute("SELECT id FROM account WHERE name = ?", (name,))
    user_row = cur.fetchone()
    user_id = user_row["id"]

    # check user progress
    cur.execute("SELECT * FROM user_progress WHERE user_id = ?", (user_id,))
    progress = cur.fetchone()

    if not progress:
        cur.execute("INSERT INTO user_progress(user_id) VALUES (?)", (user_id,))
        conn.commit()
        output_levels_cleared = 0
        output_coins = 0
    else:
        output_levels_cleared = progress["output_levels_cleared"]
        output_coins = progress["output_coins"]

    # if game already finished
    if output_levels_cleared >= len(output_levels):
        conn.close()
        return render_template("completed.html", coins=output_coins, name=name)

    level_data = output_levels[output_levels_cleared]
    message = None

    if request.method == "POST":
        user_output = request.form["user_output"].strip()

        def normalize_output(text):
            return "\n".join([line.strip() for line in text.strip().splitlines()])

        if normalize_output(user_output) == normalize_output(
            level_data["expected_output"]
        ):
            output_levels_cleared += 1
            output_coins += 999
            cur.execute(
                "UPDATE user_progress SET output_levels_cleared=?, output_coins=? WHERE user_id=?",
                (output_levels_cleared, output_coins, user_id),
            )
            conn.commit()

            if output_levels_cleared == len(output_levels):
                conn.close()
                return render_template("completed.html", coins=output_coins, name=name)
            else:
                level_data = output_levels[output_levels_cleared]
                message = "✅ Correct! Level Up!"
        else:
            message = "❌ Wrong! Try again!"

    conn.close()
    return render_template(
        "outputchallenge.html",
        level_data=level_data,
        message=message,
        name=name,
        coins=output_coins,
    )


@app.route("/writecode", methods=["GET", "POST"])
def write_code_under_time():
    name = session["p_name"]
    conn = sq.connect("database.db")
    conn.row_factory = sq.Row
    cur = conn.cursor()

    # Get user
    cur.execute("SELECT id FROM account WHERE name = ?", (name,))
    user_row = cur.fetchone()
    user_id = user_row["id"]

    # Ensure progress row
    cur.execute("SELECT * FROM user_progress WHERE user_id = ?", (user_id,))
    progress = cur.fetchone()

    if not progress:
        cur.execute(
            "INSERT INTO user_progress(user_id, write_levels_cleared, write_coins) VALUES (?, ?, ?)",
            (user_id, 0, 0),
        )
        conn.commit()
        write_levels_cleared = 0
        write_coins = 0
    else:
        write_levels_cleared = progress["write_levels_cleared"]
        write_coins = progress["write_coins"]

    # Load JSON
    WRITE_CODE_FILE = os.path.join("data", "write-code-levels.json")
    with open(WRITE_CODE_FILE, "r") as f:
        write_code_levels = json.load(f)

    # All levels done?
    if write_levels_cleared >= len(write_code_levels):
        conn.close()
        return render_template("completed.html", coins=write_coins, name=name)

    level_data = write_code_levels[write_levels_cleared]
    message = None

    if request.method == "POST":
        user_code = request.form["user_code"].strip()
        start_time = float(request.form["start_time"])
        elapsed = time.time() - start_time

        if elapsed > level_data["time_limit"]:
            message = f"⏳ Time’s up! You took {int(elapsed)}s."
        else:
            try:
                # Test against multiple test cases
                all_passed = True
                feedback = []

                for tc in level_data["test_cases"]:
                    test_input = tc["input"]
                    expected_output = tc["output"]

                    buffer = io.StringIO()
                    sys_stdout = sys.stdout
                    sys.stdout = buffer

                    try:
                        local_env = {}
                        exec(user_code, {}, local_env)
                    except Exception as e:
                        sys.stdout = sys_stdout
                        all_passed = False
                        feedback.append(f"⚠️ Error running code: {e}")
                        break

                    sys.stdout = sys_stdout
                    printed_output = buffer.getvalue().strip()

                    # Convert both to string for fair comparison
                    if str(printed_output) == str(expected_output):
                        feedback.append(f"✅ Input {test_input} → Correct")
                    else:
                        feedback.append(
                            f"❌ Input {test_input} → Expected {expected_output}, Got {printed_output}"
                        )
                        all_passed = False

                if all_passed:
                    write_levels_cleared += 1
                    write_coins += 999
                    cur.execute(
                        "UPDATE user_progress SET write_levels_cleared=?, write_coins=? WHERE user_id=?",
                        (write_levels_cleared, write_coins, user_id),
                    )
                    conn.commit()

                    if write_levels_cleared == len(write_code_levels):
                        conn.close()
                        return render_template(
                            "completed.html", coins=write_coins, name=name
                        )
                    else:
                        level_data = write_code_levels[write_levels_cleared]
                        message = "🎉 All test cases passed! Level up!"
                else:
                    message = "<br>".join(feedback)

            except Exception as e:
                message = f"⚠️ Error: {str(e)}"

    conn.close()
    return render_template(
        "writecode.html",
        level_data=level_data,
        message=message,
        name=name,
        coins=write_coins,
        start_time=time.time(),
    )


@app.route("/quizmaster", methods=["GET", "POST"])
def quiz_master():
    name = session["p_name"]
    conn = sq.connect("database.db")
    conn.row_factory = sq.Row
    cur = conn.cursor()

    # Get user
    cur.execute("SELECT id FROM account WHERE name = ?", (name,))
    user_row = cur.fetchone()
    user_id = user_row["id"]

    # Ensure progress row
    cur.execute("SELECT * FROM user_progress WHERE user_id = ?", (user_id,))
    progress = cur.fetchone()

    if not progress:
        cur.execute(
            "INSERT INTO user_progress(user_id, quiz_levels_cleared, quiz_coins) VALUES (?, ?, ?)",
            (user_id, 0, 0),
        )
        conn.commit()
        quiz_levels_cleared = 0
        quiz_coins = 0
    else:
        quiz_levels_cleared = progress["quiz_levels_cleared"]
        quiz_coins = progress["quiz_coins"]

    # All levels done?
    if quiz_levels_cleared >= len(quiz_levels):
        conn.close()
        return render_template("completed.html", coins=quiz_coins, name=name)

    level_data = quiz_levels[quiz_levels_cleared]
    message = None
    feedback = []

    if request.method == "POST":
        try:
            # which question answered
            q_index = int(request.form["q_index"])
            user_answer = int(request.form["answer"])
            correct_answer = level_data["questions"][q_index]["answer"]

            if user_answer == correct_answer:
                feedback.append(f"✅ Q{q_index+1}: Correct!")
                quiz_coins += 399
            else:
                feedback.append(
                    f"❌ Q{q_index+1}: Wrong! Correct was {level_data['questions'][q_index]['options'][correct_answer-1]}"
                )

            if q_index + 1 == len(level_data["questions"]):
                quiz_levels_cleared += 1
                cur.execute(
                    "UPDATE user_progress SET quiz_levels_cleared=?, quiz_coins=? WHERE user_id=?",
                    (quiz_levels_cleared, quiz_coins, user_id),
                )
                conn.commit()

                if quiz_levels_cleared == len(quiz_levels):
                    conn.close()
                    return render_template(
                        "completed.html", coins=quiz_coins, name=name
                    )
                else:
                    level_data = quiz_levels[quiz_levels_cleared]
                    message = "🎉 Level complete! Next level unlocked!"
                    feedback = []

            else:
                message = f"Answered Q{q_index+1}, now next!"
                return render_template(
                    "quizmaster.html",
                    level_data=level_data,
                    name=name,
                    coins=quiz_coins,
                    q_index=q_index + 1,
                    feedback=feedback,
                )
        except Exception as e:
            message = f"⚠️ Error: {e}"

    conn.close()
    return render_template(
        "quizmaster.html",
        level_data=level_data,
        name=name,
        coins=quiz_coins,
        q_index=0,
        feedback=feedback,
    )


@app.route("/dashboard")
def dashboard():
    name = session["p_name"]
    conn = sq.connect("database.db")
    conn.row_factory = sq.Row
    cur = conn.cursor()

    cur.execute("SELECT id FROM account WHERE name = ?", (name,))
    user_row = cur.fetchone()
    user_id = user_row["id"]

    cur.execute("SELECT * FROM user_progress WHERE user_id = ?", (user_id,))
    progress = cur.fetchone()
    conn.close()

    stats = {
        "Spot the Error": {
            "levels": progress["levels_cleared"],
            "coins": progress["coins"],
        },
        "Output Challenge": {
            "levels": progress["output_levels_cleared"],
            "coins": progress["output_coins"],
        },
        "Write Code": {
            "levels": progress["write_levels_cleared"],
            "coins": progress["write_coins"],
        },
        "Quiz Master": {
            "levels": progress["quiz_levels_cleared"],
            "coins": progress["quiz_coins"],
        },
    }
    return render_template("dashboard.html", name=name, stats=stats)

@app.route("/leaderboard")
def leaderboard():
    # require login (optional)
    name = session.get("p_name")
    if not name:
        return redirect("/login")

    conn = sq.connect("database.db")
    conn.row_factory = sq.Row
    cur = conn.cursor()

    # Sum coins from all modes (if user_progress row missing for some users, they won't appear)
    cur.execute("""
        SELECT a.name,
               (IFNULL(up.coins,0) + IFNULL(up.output_coins,0) + IFNULL(up.write_coins,0) + IFNULL(up.quiz_coins,0)) AS total_coins
        FROM account a
        JOIN user_progress up ON a.id = up.user_id
        ORDER BY total_coins DESC, a.name ASC
    """)
    rows = cur.fetchall()
    conn.close()

    # Convert sqlite3.Row objects to plain dicts so template access is safe
    leaderboard_data = [dict(r) for r in rows]

    # compute current user's rank (1-based)
    current_rank = None
    for idx, row in enumerate(leaderboard_data, start=1):
        if row.get("name") == name:
            current_rank = idx
            break

    return render_template("leaderboard.html",
                           leaderboard_data=leaderboard_data,
                           name=name,
                           current_rank=current_rank)



database()
app.run(debug=True)
