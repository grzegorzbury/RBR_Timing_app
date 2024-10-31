from flask import Flask, render_template, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func
from datetime import datetime
import matplotlib.pyplot as plt
import io
import base64

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///rally2.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Database Models
class Driver(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)

class Stage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    length = db.Column(db.Float, nullable=False)  # Length in km

class Car(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    car_class = db.Column(db.String(20), nullable=False)

class Rally(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    date = db.Column(db.DateTime, default=datetime.utcnow)

class RallyTime(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    rally_id = db.Column(db.Integer, db.ForeignKey('rally.id'), nullable=False)
    driver_id = db.Column(db.Integer, db.ForeignKey('driver.id'), nullable=False)
    stage_id = db.Column(db.Integer, db.ForeignKey('stage.id'), nullable=False)
    car_id = db.Column(db.Integer, db.ForeignKey('car.id'), nullable=False)
    stage_number = db.Column(db.String(10), nullable=False)  # New column for stage number
    time = db.Column(db.String(12), nullable=False)  # Time in HH:MM:SS.SS format

    # Relationships to navigate from RallyTime to Driver, Stage, Car
    rally = db.relationship('Rally', backref=db.backref('rally_times', lazy=True))
    driver = db.relationship('Driver', backref=db.backref('rally_times', lazy=True))
    stage = db.relationship('Stage', backref=db.backref('rally_times', lazy=True))
    car = db.relationship('Car', backref=db.backref('rally_times', lazy=True))


# Routes
@app.route('/')
def index():
    rallies = Rally.query.all()
    return render_template('index.html', rallies=rallies)

@app.route('/rally/<int:rally_id>')
def rally_results(rally_id):
    rally = Rally.query.get_or_404(rally_id)

    # Group times by stage number and sort each group by lowest time
    stages_with_times = (
        db.session.query(RallyTime, Stage)
        .join(Stage, Stage.id == RallyTime.stage_id)
        .filter(RallyTime.rally_id == rally_id)
        .order_by(RallyTime.stage_number, func.strftime('%H:%M:%S.%f', RallyTime.time))  # Sort by stage number, then time
        .all()
    )

    # Structure data as {stage_number: (stage_name, [times...])} for easier template rendering
    results_by_stage_number = {}
    for rally_time, stage in stages_with_times:
        stage_number = rally_time.stage_number
        if stage_number not in results_by_stage_number:
            results_by_stage_number[stage_number] = (stage.name, [])  # Store stage name and initialize times list
        results_by_stage_number[stage_number][1].append(rally_time)

    # Pass enumerate explicitly to the template
    return render_template('rally_results.html', rally=rally, results_by_stage_number=results_by_stage_number, enumerate=enumerate)


@app.route('/add_driver', methods=['GET', 'POST'])
def add_driver():
    if request.method == 'POST':
        driver_name = request.form['name']
        new_driver = Driver(name=driver_name)
        db.session.add(new_driver)
        db.session.commit()
        return redirect(url_for('index'))
    return render_template('add_driver.html')

@app.route('/add_stage', methods=['GET', 'POST'])
def add_stage():
    if request.method == 'POST':
        stage_name = request.form['name']
        stage_length = request.form['length']
        new_stage = Stage(name=stage_name, length=float(stage_length))
        db.session.add(new_stage)
        db.session.commit()
        return redirect(url_for('index'))
    return render_template('add_stage.html')

@app.route('/add_car', methods=['GET', 'POST'])
def add_car():
    if request.method == 'POST':
        car_name = request.form['name']
        car_class = request.form['class']
        new_car = Car(name=car_name, car_class=car_class)
        db.session.add(new_car)
        db.session.commit()
        return redirect(url_for('index'))
    return render_template('add_car.html')

@app.route('/add_rally', methods=['GET', 'POST'])
def add_rally():
    if request.method == 'POST':
        rally_name = request.form['name']
        new_rally = Rally(name=rally_name)
        db.session.add(new_rally)
        db.session.commit()
        return redirect(url_for('index'))
    return render_template('add_rally.html')

@app.route('/add_time', methods=['GET', 'POST'])
def add_time():
    if request.method == 'POST':
        rally_id = request.form['rally']
        driver_id = request.form['driver']
        stage_id = request.form['stage']
        car_id = request.form['car']
        stage_number = request.form['stage_number']  # Capture the stage number
        time = request.form['time']

        # Create and add new RallyTime entry
        rally_time = RallyTime(
            rally_id=rally_id,
            driver_id=driver_id,
            stage_id=stage_id,
            car_id=car_id,
            stage_number=stage_number,  # Save the stage number
            time=time
        )
        db.session.add(rally_time)
        db.session.commit()
        
        return redirect(url_for('index'))

    # Pass all options to the template for selection
    rallies = Rally.query.all()
    drivers = Driver.query.all()
    stages = Stage.query.all()
    cars = Car.query.all()
    
    return render_template('add_time.html', rallies=rallies, drivers=drivers, stages=stages, cars=cars)


@app.route('/plot/<int:rally_id>')
def plot(rally_id):
    times = RallyTime.query.filter_by(rally_id=rally_id).all()
    driver_times = {}
    
    for time_entry in times:
        driver = Driver.query.get(time_entry.driver_id).name
        time_parts = time_entry.time.split(':')
        total_seconds = int(time_parts[0]) * 3600 + int(time_parts[1]) * 60 + float(time_parts[2])
        if driver in driver_times:
            driver_times[driver].append(total_seconds)
        else:
            driver_times[driver] = [total_seconds]
    
    fig, ax = plt.subplots()
    for i, (driver, times) in enumerate(driver_times.items()):
        ax.plot([i] * len(times), times, 'o', label=driver)
    
    ax.set_xlabel("Drivers")
    ax.set_ylabel("Time (seconds)")
    ax.legend(loc="upper left", bbox_to_anchor=(1, 1))
    plt.xticks(range(len(driver_times)), list(driver_times.keys()), rotation=45)

    img = io.BytesIO()
    plt.savefig(img, format='png', bbox_inches="tight")
    img.seek(0)
    plot_url = base64.b64encode(img.getvalue()).decode()

    return render_template('plot.html', plot_url=plot_url)

# Initialize database
@app.before_first_request
def create_tables():
    db.create_all()

if __name__ == '__main__':
    app.run(debug=True)
