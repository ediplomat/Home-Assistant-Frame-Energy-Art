# The Story Behind Frame Energy Art

## How it started

This project started with a simple problem in my own home.

I use Home Assistant to watch my home energy: solar production, electricity
use, the home battery and our two electric cars. Everything was there, but to
see it I had to open the app on my iPhone or sit at the computer every time.

It worked, but it was not convenient. I wanted to see the important things just
by walking past.

## Looking for a better way

I looked at what other people in the Home Assistant community do: tablets on
the wall, small screens, special dashboard displays. Many good ideas, but all
of them needed one more device, one more power cable and one more screen in
the house.

Then I looked at my Samsung The Frame. It already hangs on the wall and shows
paintings when nobody watches TV.

So I asked myself: why buy another screen? What if the painting itself could
show my home?

That was the beginning of this project.

## A painting, not a dashboard

I did not want to turn the TV into one more dashboard with buttons, cards and
graphs. There are already many good ones.

The painting had to stay the main thing. The numbers had to become part of the
picture: in the sky, in the colours of the painting, in a calm serif font, with
no boxes around them.

For the cars I used only the first letters, T and H. You can still see which
car is which, but the picture does not turn into an advert full of logos.

## Making it update by itself

A real painting never changes, but my home does, all day.

I wrote a Home Assistant integration in Python. It takes the latest values,
paints them onto the background picture and sends the new picture to the TV.
An automation runs it every 15 minutes. That is fresh enough, and the TV is
not flooded with pictures.

## The pictures that would not stop

The TV part was the hardest. Every upload added a new picture to the TV and
nothing removed the old ones. I could see the numbers grow: MY_F0010,
MY_F0011, and later almost thirty pictures of the same painting in My Photos.
With an update every 15 minutes that would be almost a hundred pictures a day,
until the TV memory was full.

So I wrote my own connection to the TV. Now every update:

1. sends the new picture and waits until the TV confirms it;
2. shows it on the screen;
3. deletes the previous picture made by the project.

My own photos and artworks on the TV are never touched. If a delete does not
work, the integration remembers it and tries again next time. If the TV does
not confirm the new picture, Home Assistant shows an error instead of
pretending that everything is fine.

I tested it on my kitchen Frame: picture MY_F0028 was deleted as soon as
MY_F0029 arrived. After a successful update the previous picture is deleted.
If the delete fails, the integration tries again on the next update.

There was one more surprise. I expected the TV to ask "Allow?" the first time,
but my 2019 Frame opens Art Mode without any token. My first version thought
this was an error. The logs showed the real reason, and the fix was to accept
it as a normal case.

## The TV that switched off the news

One evening I was watching the news on the kitchen TV. Suddenly the picture
went away and the painting appeared. It happened exactly at a scheduled
update: my integration had told the TV to show the new picture, and the TV
did it, even in the middle of the news.

In my tests the TV was always already in Art Mode, so I never saw this. Now,
before showing the picture, the integration asks the TV if Art Mode is on. If
somebody is watching TV, the new picture is only set as the current artwork
and appears later, when the TV goes back to Art Mode. This was version 1.1.1.

## Why I removed the clock

At first I had a clock in the picture. It looked useful.

Then I understood: the picture changes only every 15 minutes. The clock would
show 14:00 when it is already 14:12. A clock that is wrong most of the time is
worse than no clock.

I changed it to the time of the last update. Later I removed that too, because
even a small timestamp made the picture look like a screen again. Now there is
only the date.

Good design is not about adding as many features as possible. Sometimes
removing something makes the project better.

Later I understood that other people may want it differently. In version
1.2.0 the update time came back as an option, off by default and small, above
the date. In the same version the painting moved inside the integration, so
it works right after installing, and people with one car or no car get a
balanced picture without empty columns.

## What I learned

This project was more than putting numbers on a TV. I had to:

- draw the picture with Python so it stays readable but still looks like art;
- handle missing or wrong sensor values without breaking the picture;
- talk to the TV directly over the local network and check that it really got
  the picture;
- read logs to find the real reason when something fails;
- test the code with a fake TV, so the tests do not need a real television.

Not everything worked the first time. Some ideas I changed, some I removed.
That is normal in a real project. I learned that the technical part must work
together with the design and with how people really live with it.

## Education and why I published it

I finished a Pearson BTEC Level 4 HNC in Computing (Cyber Security) with
Merit, and now I study MEng Autonomous Robotics at NMITE in Hereford.

I like networks, automation and practical problems. I wanted to build
something useful outside the classroom, and this project became one of my
personal projects.

I put it on GitHub to build my technical portfolio, to show how I work, and to
share it with the Home Assistant community. I would be happy to get feedback
and learn from other people.

## Final thought

It started with a simple question: is there an easier way to check my Home
Assistant? It became a better one: what if the dashboard could be a painting?

The project is still growing.
