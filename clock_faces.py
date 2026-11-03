"""Native clock/date designs. Time is supplied by the shared player/preview context."""
import calendar
import math
from datetime import timedelta, timezone

from clock_canvas import Canvas, shade
from render import FONT_FAMILIES, FONT_SIZES

DESIGN_NAMES = {
    'platform': 'Platform', 'station': 'Station', 'time_stack': 'Time Stack',
    'perpetual_card': 'Perpetual Card', 'week_strip': 'Week Strip',
    'date_poster': 'Date Poster', 'month_map': 'Month Map', 'tracker': 'Tracker',
    'orbit': 'Orbit', 'word_glow': 'Word Glow', 'clockwork': 'Clockwork', 'minute_runner': 'Minute Runner',
}
LEGACY_TRACKER_UNITS = {'minute_track': 'minutes', 'seconds_track': 'seconds'}
DESIGN_ACCENTS = {name: '#FFB34D' for name in DESIGN_NAMES}
DESIGN_ACCENTS.update(station='#FF645B', perpetual_card='#FF645B',
                      week_strip='#59DBCD', date_poster='#B994FF', word_glow='#59DBCD')
WEEKDAYS = ('MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT', 'SUN')
MONTHS = ('JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC')
HOURS = ('TWELVE', 'ONE', 'TWO', 'THREE', 'FOUR', 'FIVE', 'SIX', 'SEVEN', 'EIGHT', 'NINE', 'TEN', 'ELEVEN')
SMALL = ('', 'ONE', 'TWO', 'THREE', 'FOUR', 'FIVE', 'SIX', 'SEVEN', 'EIGHT', 'NINE',
         'TEN', 'ELEVEN', 'TWELVE', 'THIRTEEN', 'FOURTEEN', 'FIFTEEN', 'SIXTEEN', 'SEVENTEEN', 'EIGHTEEN', 'NINETEEN')
TENS = ('', '', 'TWENTY', 'THIRTY', 'FORTY', 'FIFTY')
SECONDS_READOUT_DESIGNS = ('platform', 'time_stack', 'tracker', 'clockwork', 'perpetual_card', 'week_strip')


def week_dates(now):
    monday = now.date() - timedelta(days=now.weekday())
    return [monday + timedelta(days=i) for i in range(7)]


def month_cells(now):
    return calendar.Calendar(firstweekday=0).monthdayscalendar(now.year, now.month)


def previous_minute(now):
    # Local subtraction invents/skips an hour at DST boundaries. Move on the
    # actual timeline, then convert back to the supplied display timezone.
    if now.utcoffset() is not None:
        return (now.astimezone(timezone.utc) - timedelta(minutes=1)).astimezone(now.tzinfo)
    return now - timedelta(minutes=1)


def time_words(now):
    minute = now.minute
    if minute == 0:
        tens, units = "O'CLOCK", ''
    elif minute < 10:
        tens, units = 'OH', SMALL[minute]
    elif minute < 20:
        tens, units = SMALL[minute], ''
    else:
        tens, units = TENS[minute // 10], SMALL[minute % 10]
    return 'IT IS', HOURS[now.hour % 12], tens, units


# Two hands per dial, six dials per numeral, clockwise from the right.
R, D, L, U = 0, math.pi / 2, math.pi, 3 * math.pi / 2
DIAL_DIGITS = {
    '0': ((R, D), (L, D), (U, D), (U, D), (U, R), (U, L)),
    '1': (None, (D, D), None, (U, D), None, (U, U)),
    '2': ((R, R), (L, D), (R, D), (U, L), (U, R), (L, L)),
    '3': ((R, R), (L, D), (R, R), (U, L), (R, R), (U, L)),
    '4': ((D, D), (D, D), (U, R), (U, D), None, (U, U)),
    '5': ((R, D), (L, L), (U, R), (L, D), (R, R), (U, L)),
    '6': ((R, D), (L, L), (U, D), (L, D), (U, R), (U, L)),
    '7': ((R, R), (L, D), None, (U, D), None, (U, U)),
    '8': ((R, D), (L, D), (U, R), (U, L), (U, R), (U, L)),
    '9': ((R, D), (L, D), (U, R), (U, D), (R, R), (U, L)),
}


class Face:
    def __init__(self, now, h24, show_date, show_seconds, animate, primary, accent, tinted, custom_accent, seconds_display,
                 font_family, font_size, track_unit):
        self.c = Canvas()
        self.now, self.h24, self.show_date = now, h24, show_date
        self.show_seconds, self.animate = show_seconds, animate
        self.seconds_display = seconds_display
        self.track_unit = track_unit
        self.font_family = font_family if font_family in FONT_FAMILIES else 'standard'
        self.font_size = font_size if font_size in FONT_SIZES else 'auto'
        self.primary = primary
        self.accent = accent
        self.dim, self.faint = shade(primary, .45), shade(primary, .20)
        self.teal = accent if tinted or custom_accent else '#59DBCD'
        self.blue = primary if tinted else '#7EBCFF'
        self.purple = accent if tinted or custom_accent else '#B994FF'
        self.red = accent if tinted or custom_accent else '#FF645B'
        self.phase = now.second + (now.microsecond / 1e6 if animate else 0)
        self.second = self.phase if show_seconds else 0
        self.hour = f'{now.hour if h24 else now.hour % 12 or 12:02}'
        self.minute = f'{now.minute:02}'
        self.time = f'{self.hour}:{self.minute}'
        self.day, self.month = WEEKDAYS[now.weekday()], MONTHS[now.month - 1]
        self.date = f'{self.day} {now.day:02} {self.month}'
        self.ampm = '' if h24 else ('AM' if now.hour < 12 else 'PM')

    def text(self, value, x, y, w, h, color=None, font='3x5', face=None, size='large', **kwargs):
        self.c.text(value, x, y, w, h, self.primary if color is None else color, font, face, size, **kwargs)

    def footer(self):
        if self.seconds_display == 'number':
            if self.show_date: self.text(self.date, 0, 27, 50, 5, self.dim)
            self.text(f':{self.now.second:02}', 53, 27, 11, 5, self.teal)
        elif self.seconds_display == 'bar':
            if self.show_date: self.text(self.date, 0, 26, 64, 5, self.dim)
            self.seconds_bar(0, 31, 64)
        elif self.show_date:
            self.text(self.date, 0, 27, 64, 5, self.dim)

    def seconds_bar(self, x, y, width):
        self.c.line(x, y, x + width - 1, y, self.faint)
        filled = int(self.phase * width / 60)
        if filled: self.c.line(x, y, x + filled - 1, y, self.teal)

    def seconds_label(self):
        return f'{self.ampm} :{self.now.second:02}'.strip() if self.seconds_display == 'number' else self.ampm

    def platform(self):
        old = previous_minute(self.now)
        old_values = (f'{old.hour if self.h24 else old.hour % 12 or 12:02}', f'{old.minute:02}')
        for x, value, previous in zip((0, 35), (self.hour, self.minute), old_values):
            self.c.rect(x, 0, x + 28, 25, shade(self.primary, .07))
            self.c.rect(x + 1, 14, x + 27, 24, shade(self.primary, .10))
            scale = 1
            if self.animate and self.phase < .4 and value != previous:
                p = self.phase / .4
                if p < .5:
                    value, scale = previous, 1 - p * 2
                else:
                    scale = (p - .5) * 2
            self.text(value, x + 1, 1, 27, 23, face='standard', size='xl', scale_y=scale)
            self.c.line(x, 13, x + 28, 13, (0, 0, 0))
            self.c.rect(x, 12, x + 1, 14, self.dim)
            self.c.rect(x + 27, 12, x + 28, 14, self.dim)
        for y in (9, 17): self.c.rect(31, y, 32, y + 1, self.accent)
        self.footer()

    def station(self):
        self.c.arc(15, 16, 15, 1, self.faint)
        for i in range(12):
            angle = i * math.tau / 12 - math.pi / 2
            inner = 11 if i % 3 == 0 else 12
            self.c.line(15 + inner * math.cos(angle), 16 + inner * math.sin(angle),
                        15 + 13 * math.cos(angle), 16 + 13 * math.sin(angle), self.primary)
        self.c.hand(15, 16, (self.now.hour % 12 + self.now.minute / 60) / 12, 7, self.primary, 2)
        self.c.hand(15, 16, (self.now.minute + self.second / 60) / 60, 11, self.primary)
        if self.show_seconds: self.c.hand(15, 16, self.second / 60, 12, self.red)
        self.c.rect(14, 15, 16, 17, self.red)
        self.text(self.time, 33, 2, 31, 7, font='5x7')
        if self.show_date:
            self.text(self.day, 33, 13, 31, 7, font='5x7')
            self.text(f'{self.now.day:02} {self.month}', 33, 25, 31, 5, self.red)
        else:
            self.text(self.ampm, 33, 23, 31, 5, self.dim)

    def time_stack(self):
        self.text(self.hour, 0, 0, 28, 22, self.blue, face='block', size='xl')
        self.text(self.minute, 35, 10, 29, 22, face='block', size='xl')
        for y in (11, 18): self.c.rect(30, y, 31, y + 1, self.blue)
        if self.show_date:
            self.text(self.day, 35, 0, 29, 5, self.accent)
            self.text(f'{self.month} {self.now.day:02}', 35, 6, 29, 5, self.dim)
        self.text(self.seconds_label(), 0, 26, 28, 5, self.teal if self.seconds_display == 'number' else self.dim)
        if self.seconds_display == 'bar': self.seconds_bar(0, 31, 28)

    def orbit(self):
        for radius, fraction, color in (
                (15, (self.now.hour % 12 + self.now.minute / 60) / 12, self.accent),
                (11, (self.now.minute + self.second / 60) / 60, self.teal),
                (7, self.second / 60, self.purple)):
            self.c.arc(15, 16, radius, 1, self.faint)
            self.c.arc(15, 16, radius, fraction, color)
        self.c.rect(14, 15, 16, 17, self.primary)
        self.text(self.time, 33, 2, 31, 7, font='5x7')
        if self.show_date:
            self.text(self.day, 33, 14, 31, 5, self.teal)
            self.text(f'{self.now.day:02} {self.month}', 33, 24, 31, 5, self.dim)
        else:
            self.text(self.ampm, 33, 24, 31, 5, self.dim)

    def tracker(self):
        if self.track_unit == 'seconds':
            self.seconds_track()
        else:
            self.minute_track()

    def minute_track(self):
        self.track(self.now.minute, (1 - self.phase / .5) * 8 if self.animate and self.phase < .5 else 0)

    def seconds_track(self):
        fraction = self.now.microsecond / 1e6
        shift = (1 - fraction / .25) * 8 if self.animate and fraction < .25 else 0
        self.track(self.now.second, shift)

    def track(self, value, shift):
        # Larger clocks use a compact pointer/baseline so the ruler stays fully
        # visible. With no footer, Max can use five more rows for the time.
        height = 14
        if self.font_size == 'xl':
            height = 20
        elif self.font_size == 'max':
            height = 20 if self.show_date or self.seconds_display != 'off' else 25
        clock = f'{self.hour if self.h24 else self.now.hour % 12 or 12}:{self.minute}'
        self.text(clock, 0, 0, 64, height, face=self.font_family,
                  size='large' if self.font_size == 'auto' else self.font_size)
        if height == 14:
            for y in range(3): self.c.line(30 + y, 15 + y, 34 - y, 15 + y, self.teal)
            digits_y, tick_y, baseline_y = 18, 24, 25
        else:
            self.c.point(32, height, self.teal)
            digits_y, tick_y, baseline_y = height + 1, height + 6, height + 6
        self.c.line(3, baseline_y, 60, baseline_y, self.faint)
        for delta in range(-4, 5):
            x = round(32 + delta * 8 + shift)
            self.text(f'{(value + delta) % 60:02}', x - 3, digits_y, 7, 5,
                      self.teal if delta == 0 else self.dim)
            self.c.point(x, tick_y, self.teal if delta == 0 else self.dim)
        self.footer()

    def clockwork(self):
        previous = previous_minute(self.now)
        old_hour = previous.hour if self.h24 else previous.hour % 12 or 12
        old_digits = f'{old_hour:02}{previous.minute:02}'
        for di, digit in enumerate(self.hour + self.minute):
            for k, hands in enumerate(DIAL_DIGITS[digit]):
                cx, cy = di * 16 + (k % 2) * 8 + 3, (k // 2) * 8 + 3
                self.c.arc(cx, cy, 3, 1, self.faint)
                color = self.primary if hands else self.faint
                for hi, angle in enumerate(hands or (math.pi / 4, math.pi / 4)):
                    if self.animate and self.phase < 1.5 and old_digits[di] != digit:
                        angle += (1 - self.phase / 1.5) * (math.tau + (di + k + hi) * .47)
                    self.c.line(cx, cy, cx + 3 * math.cos(angle), cy + 3 * math.sin(angle), color)
        self.c.point(31, 8, self.accent)
        self.c.point(31, 16, self.accent)
        self.footer()

    def perpetual_card(self):
        self.c.rect(0, 0, 26, 31, self.faint, outline=True)
        self.c.rect(1, 1, 25, 7, self.red)
        self.text(self.day, 1, 2, 25, 5, (0, 0, 0))
        self.text(f'{self.now.day:02}', 1, 9, 25, 22, face='block', size='xl')
        self.text(self.time, 30, 1, 34, 12, face='standard', size='medium')
        self.text(self.seconds_label(), 30, 15, 34, 5, self.teal if self.seconds_display == 'number' else self.dim)
        if self.seconds_display == 'bar': self.seconds_bar(30, 21, 34)
        self.text(self.month, 30, 24, 34, 7, self.red, font='5x7')

    def week_strip(self):
        self.text(f'{self.month} {self.now.year}', 0, 0, 64, 5, self.dim)
        value = self.time + (f':{self.now.second:02}' if self.seconds_display == 'number' else '')
        self.text(value, 0, 6, 64, 12, face='standard', size='medium')
        if self.seconds_display == 'bar': self.seconds_bar(0, 18, 64)
        for i, day in enumerate(week_dates(self.now)):
            x, today = i * 9, day == self.now.date()
            if today: self.c.rect(x, 20, x + 8, 31, shade(self.teal, .32))
            self.text('MTWTFSS'[i], x + 1, 21, 7, 5, self.teal if today else self.dim)
            self.text(f'{day.day:02}', x + 1, 26, 7, 5, self.primary if today else self.dim)

    def month_map(self):
        self.text(self.month, 0, 0, 25, 5, self.teal)
        self.text(f'{self.now.day:02}', 0, 6, 25, 21, face='standard', size='xl')
        self.text(str(self.now.year), 0, 27, 25, 5, self.dim)
        for col, label in enumerate('MTWTFSS'): self.text(label, 29 + col * 5, 0, 3, 5, self.dim)
        for row, week in enumerate(month_cells(self.now)):
            for col, day in enumerate(week):
                if day:
                    color = self.accent if day == self.now.day else shade(self.teal, .45) if day < self.now.day else shade(self.primary, .30)
                    self.c.rect(29 + col * 5, 7 + row * 4, 31 + col * 5, 9 + row * 4, color)

    def date_poster(self):
        self.text(f'{self.now.day:02}', 0, 0, 40, 32, face='block', size='max')
        self.text(self.day, 43, 1, 21, 7, self.purple, font='5x7')
        self.text(self.month, 43, 13, 21, 7, self.purple, font='5x7')
        self.text(str(self.now.year), 43, 26, 21, 5, self.dim)

    def word_glow(self):
        # This is a digital word field: filler letters reflow to fit the exact minute.
        for row, word in enumerate(time_words(self.now)):
            offset = (10 - len(word)) // 2
            filler = 'QPLUMBWOLF'
            for col in range(10):
                active = offset <= col < offset + len(word) and word[col - offset] != ' '
                char = word[col - offset] if offset <= col < offset + len(word) else filler[(col + row * 3) % 10]
                self.text(char, 2 + col * 6, row * 8, 5, 7, self.teal if active else self.faint, font='5x7')

    def minute_runner(self):
        self.text(self.time, 0, 0, 64, 15, self.accent, face='block', size='large')
        if self.show_date: self.text(self.date, 0, 17, 64, 5, self.dim)
        self.c.line(0, 31, 63, 31, shade(self.teal, .45))
        for x in range(0, 64, 8): self.c.line(x, 30, x + 3, 30, self.faint)
        x = 1 + round(self.second / 60 * 56)
        for coin in (12, 25, 39, 51):
            if coin > x: self.c.rect(coin, 24, coin + 1, 25, self.accent)
        y = 24 - (int(self.second * 4) % 2 if self.animate and self.show_seconds else 0)
        self.c.rect(x, y, x + 2, y + 2, self.teal)
        self.c.line(x + 1, y + 3, x + 1, y + 4, self.teal)
        self.c.line(x, y + 5, x - 1, y + 6, self.teal)
        self.c.line(x + 2, y + 5, x + 3, y + 6, self.teal)
        self.c.line(60, 23, 60, 30, self.primary)
        self.c.rect(61, 23, 63, 24, self.purple)
        self.c.point(61, 25, self.purple)


def draw_face(design, now, *, h24=False, show_date=True, show_seconds=True, animate=True,
              primary='#F4F2EE', accent=None, tinted=False, seconds_display='off',
              font_family='standard', font_size='auto', track_unit=None):
    """Return one opaque native frame. Never reads clocks, providers, files, or hardware."""
    unit = track_unit if track_unit in ('minutes', 'seconds') else LEGACY_TRACKER_UNITS.get(design, 'minutes')
    design = 'tracker' if design in LEGACY_TRACKER_UNITS else design
    seconds_readout = design in SECONDS_READOUT_DESIGNS and not (design == 'tracker' and unit == 'seconds')
    face = Face(now, h24, show_date, show_seconds, animate, primary,
                accent or DESIGN_ACCENTS.get(design, '#FFB34D'), tinted, accent is not None,
                seconds_display if seconds_readout and seconds_display in ('number', 'bar') else 'off',
                font_family, font_size, unit)
    getattr(face, design if design in DESIGN_NAMES else 'platform')()
    return face.c.pixels
