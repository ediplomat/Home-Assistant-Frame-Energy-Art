"""Deterministic live values over a clean Tuscan background."""
from pathlib import Path
from datetime import datetime
import math
import os
import tempfile
from PIL import Image, ImageDraw, ImageFont, ImageOps

INK = "#444936"
GREEN = "#526846"
GOLD = "#c49631"
# Darker than the sky so clouds stay readable on warm backgrounds yet look painted.
CLOUD = "#8a8678"
RIGHT_EDGE = 1900
# Shipped inside the integration, so HACS users have a picture from the start.
BUILTIN_BACKGROUND = Path(__file__).parent / "backgrounds" / "tuscan_background.jpg"
QUIET = "#6f6c5c"  # softer than INK, for the optional update time
LABEL_DEFAULTS = {
    "vehicle1_name": "Tesla",
    "vehicle1_letter": "T",
    "vehicle2_name": "Hyundai IONIQ 6",
    "vehicle2_letter": "H",
    "location_name": "Local weather",
}
WEATHER_NAMES = {"cloudy":"Cloudy", "partlycloudy":"Partly cloudy", "sunny":"Sunny", "clear-night":"Clear night", "rainy":"Rain", "pouring":"Heavy rain", "lightning-rainy":"Thunderstorms", "lightning":"Thunderstorms", "snowy":"Snow", "snowy-rainy":"Sleet", "fog":"Fog", "windy":"Windy", "windy-variant":"Windy", "exceptional":"Weather alert"}

def finite(value):
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except (ValueError, TypeError):
        return None

def numeric(snapshot, key, power=False):
    item = snapshot.get(key) or {}
    value = finite(item.get("state"))
    if value is not None and power:
        unit = item.get("attributes", {}).get("unit_of_measurement")
        if unit == "W":
            value /= 1000
        elif unit != "kW":
            return None
    if not power and value is not None and not 0 <= value <= 100:
        return None
    return value

def power_text(value):
    return "—" if value is None else f"{value:.2f} kW"

def percent_text(value):
    return "—" if value is None else f"{value:.0f}%"

def load_font(size):
    candidates = [str(Path(__file__).parent / "fonts" / "DejaVuSerif.ttf"), "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf", "/usr/share/fonts/TTF/DejaVuSerif.ttf", "/usr/share/fonts/dejavu/DejaVuSerif.ttf", "/usr/share/fonts/truetype/liberation2/LiberationSerif-Regular.ttf", "/usr/share/fonts/liberation/LiberationSerif-Regular.ttf"]
    for path in candidates:
        if Path(path).is_file():
            return ImageFont.truetype(path, size)
    # Pillow's bundled font fallback scales to the requested size.
    return ImageFont.load_default(size=size)

def draw_weather(d, cx, cy, condition, scale=1):
    s = scale
    def cloud(x, y):
        fill = CLOUD
        for a,b,r in [(x-19*s,y,18*s),(x,y-9*s,24*s),(x+23*s,y+1*s,17*s)]:
            d.ellipse((a-r,b-r,a+r,b+r),fill=fill)
        d.rounded_rectangle((x-31*s,y,x+32*s,y+18*s),radius=9*s,fill=fill)
    def sun(x,y):
        r=18*s
        d.ellipse((x-r,y-r,x+r,y+r),fill=GOLD)
        for i in range(8):
            a=i*math.pi/4
            d.line((x+25*s*math.cos(a),y+25*s*math.sin(a),x+33*s*math.cos(a),y+33*s*math.sin(a)),fill=GOLD,width=max(2,int(3*s)))
    if condition in ("sunny",):
        sun(cx,cy)
    elif condition == "clear-night":
        d.ellipse((cx-22*s,cy-22*s,cx+22*s,cy+22*s),fill=GOLD)
        d.ellipse((cx-9*s,cy-27*s,cx+30*s,cy+12*s),fill="#e7d5b3")
    elif condition in WEATHER_NAMES:
        if condition == "partlycloudy":
            sun(cx+15*s,cy-13*s)
        cloud(cx,cy)
        if condition in ("rainy","pouring","lightning-rainy","snowy-rainy"):
            for x in (-16,0,16):
                d.line((cx+x*s,cy+27*s,cx+(x-5)*s,cy+38*s),fill="#7b8c8e",width=max(2,int(3*s)))
        if condition == "snowy":
            for x in (-16,0,16):
                d.text((cx+x*s,cy+27*s),"*",font=load_font(int(20*s)),fill=INK,anchor="mm")
    else:
        d.text((cx,cy),"—",font=load_font(int(32*s)),fill=INK,anchor="mm")

def column_width(x, width=245):
    """Keep centred text inside the frame: never wider than twice the gap to the edge."""
    return min(width, 2 * (RIGHT_EDGE - x))

CARS = (("tesla", "vehicle1", 68), ("hyundai", "vehicle2", 52))  # key, label prefix, monogram size
FIVE_COLUMNS = [710, 990, 1270, 1540, 1800]  # the original layout with two cars
COLUMN_GAP = 280
COLUMN_CENTRE = 1255  # middle of the original row


def column_positions(count):
    """Two cars keep the original layout; with fewer cars the row is centred."""
    if count == len(FIVE_COLUMNS):
        return list(FIVE_COLUMNS)
    first = COLUMN_CENTRE - COLUMN_GAP * (count - 1) / 2
    return [round(first + COLUMN_GAP * i) for i in range(count)]


def render(background, output, snapshot, forecast, now, labels=None, cars=None, show_update_time=False):
    """``cars`` lists the enabled car keys ("tesla", "hyundai"); None means both.

    An empty ``background`` uses the built-in painting. ``show_update_time``
    adds a small "Updated HH:MM" under the date (off by default: the picture
    should look like a painting, not a screen).
    """
    labels = {**LABEL_DEFAULTS, **{k: v for k, v in (labels or {}).items() if v}}
    enabled = [car for car in CARS if cars is None or car[0] in cars]
    with Image.open(background or BUILTIN_BACKGROUND) as source:
        im = ImageOps.fit(source.convert("RGB"), (1920,1080), method=Image.Resampling.LANCZOS)
    d = ImageDraw.Draw(im)
    def text(x,y,value,size=26,anchor="mm",fill=INK,max_width=None):
        size=int(size)
        while max_width and size>16 and d.textbbox((0,0),str(value),font=load_font(size))[2]>max_width:
            size-=1
        d.text((x,y),str(value),font=load_font(size),fill=fill,anchor=anchor)
    text(75,204,f"{now:%A}, {now.day} {now:%B %Y}",29,"lt",max_width=485)
    if show_update_time:
        text(75,166,f"Updated {now:%H:%M}",22,"lt",fill=QUIET)  # above the date: clear sky, away from the trees
    names=[("Solar generation","solar"),("Home consumption","home"),("Home battery","battery")]
    names+=[(labels[f"{prefix}_name"],key) for key,prefix,_ in enabled]
    xs=column_positions(len(names))
    columns=[(x,label,key) for x,(label,key) in zip(xs,names)]
    sx,hx,bx=xs[:3]
    # Simple icons are drawn by code so their meaning never changes with data.
    draw_weather(d,sx,110,"sunny",1.15)
    d.polygon([(hx-32,113),(hx,82),(hx+32,113),(hx+23,113),(hx+23,147),(hx-23,147),(hx-23,113)],fill=INK)
    d.rectangle((hx-7,123,hx+6,147),fill="#e7d5b3")
    d.rounded_rectangle((bx-20,82,bx+20,147),radius=4,outline=INK,width=4)
    d.rectangle((bx-7,75,bx+7,81),fill=INK)
    b=numeric(snapshot,"battery")
    if b is not None:
        d.rectangle((bx-14,141-int(53*b/100),bx+14,141),fill=GREEN)
    # Monograms instead of brand logos: recognisable, but the picture stays a painting.
    for x,(key,prefix,size) in zip(xs[3:],enabled):
        text(x,112,labels[f"{prefix}_letter"][:2],size)
    for index,(x,label,key) in enumerate(columns):
        value=numeric(snapshot,key,power=key in ("solar","home"))
        text(x,207,power_text(value) if key in ("solar","home") else percent_text(value),56,max_width=column_width(x))
        text(x,266,label,25,max_width=column_width(x))
        if index < len(columns)-1:
            d.line((x+142,85,x+142,306),fill="#b8ad92",width=1)
    charge=numeric(snapshot,"battery_charge",True)
    discharge=numeric(snapshot,"battery_discharge",True)
    if charge is None or discharge is None:
        detail="Power unavailable"
    elif charge>0.03:
        detail=f"Charging · {power_text(charge)}"
    elif discharge>0.03:
        detail=f"Discharging · {power_text(discharge)}"
    else:
        detail="Idle"
    text(bx,304,detail,23,fill=GREEN,max_width=245)
    for x,(key,_,_) in zip(xs[3:],enabled):
        p=numeric(snapshot,f"{key}_power",True)
        text(x,304,"—" if p is None else (f"Charging · {power_text(p)}" if p>0.05 else "Not charging"),22,max_width=column_width(x))
    weather=snapshot.get("weather") or {}
    attrs=weather.get("attributes",{})
    condition=weather.get("state","")
    draw_weather(d,1567,470,condition,1.25)
    temp=finite(attrs.get("temperature"))
    unit=attrs.get("temperature_unit", "")
    text(1718,467,"—" if temp is None else f"{temp:.0f}°",88)
    text(1718,559,WEATHER_NAMES.get(condition,"Weather unavailable"),30,max_width=340)
    text(1718,600,labels["location_name"],24,max_width=340)
    text(1870,457,unit or "",20)
    d.line((1510,665,1880,665),fill="#a79b82",width=2)
    future=[]
    today=now.date()
    for item in forecast:
        try:
            stamp=datetime.fromisoformat(item["datetime"].replace("Z","+00:00"))
            if stamp.tzinfo is not None:
                stamp=stamp.astimezone(now.tzinfo)
            if stamp.date()>today:
                future.append((stamp,item))
        except (KeyError, ValueError, TypeError):
            continue
    future.sort(key=lambda item:item[0])
    for i,x in enumerate((1536,1642,1748,1854)):
        if i<len(future):
            stamp,item=future[i]
            text(x,723,stamp.strftime("%a"),25)
            draw_weather(d,x,784,item.get("condition",""),.64)
            high=finite(item.get("temperature"))
            text(x,853,"—" if high is None else f"{high:.0f}°",33)
        else:
            text(x,782,"—",32)
    out=Path(output)
    out.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.NamedTemporaryFile(prefix=".frame_energy_",suffix=".jpg",dir=out.parent,delete=False) as f:
        tmp=Path(f.name)
    try:
        im.save(tmp,"JPEG",quality=93,subsampling=0)
        os.replace(tmp,out)
    finally:
        tmp.unlink(missing_ok=True)
