import threading
from flask import Flask
# আপনার বটের মেইন ফাইল বা ফাংশন এখানে ইম্পোর্ট করতে পারেন 
# যেমন আপনার বট রান করার ফাইল যদি bot.py হয়:
# import bot

app = Flask(__name__)

@app.route('/')
def home():
    return """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Bot Status</title>
        <style>
            body {
                background-color: #0f172a;
                color: #f8fafc;
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                display: flex;
                justify-content: center;
                align-items: center;
                height: 100vh;
                margin: 0;
            }
            .card {
                background: #1e293b;
                padding: 40px;
                border-radius: 16px;
                box-shadow: 0 10px 25px rgba(0,0,0,0.3);
                text-align: center;
                max-width: 400px;
                width: 100%;
                border: 1px solid #334155;
            }
            h1 { color: #38bdf8; margin-bottom: 10px; font-size: 26px; }
            p { color: #94a3b8; font-size: 16px; }
            .status {
                display: inline-block;
                background: #065f46;
                color: #34d399;
                padding: 6px 14px;
                border-radius: 20px;
                font-size: 14px;
                font-weight: bold;
                margin-top: 15px;
            }
        </style>
    </head>
    <body>
        <div class="card">
            <h1>Welcome! 👋</h1>
            <p>Your Telegram Bot Server is live and running smoothly on Render.</p>
            <div class="status">● Status: Active & Online</div>
        </div>
    </body>
    </html>
    """

def run_flask():
    # Render-এর দেওয়া পোর্ট অনুযায়ী ফ্লাস্ক রান করবে
    app.run(host='0.0.0.0', port=10000)

if __name__ == '__main__':
    # ফ্লাস্ক সার্ভার আলাদা থ্রেডে চালু হবে
    t = threading.Thread(target=run_flask)
    t.start()
    
    print("Web server started successfully!")
    
    # আপনার টেলিগ্রাম বট স্টার্ট করার কোড বা ফাংশন এখানে কল করতে পারেন
    # যেমন: bot.main() অথবা নিচের মতো করে আপনার বট ফাইল রান করতে পারেন:
    import os
    os.system("python bot.py")
