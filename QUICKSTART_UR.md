# Intellectual Nexus Academy — shuru kaise karein

Yeh Python + PySide6 ki **offline desktop app** hai. Aap isay PyCharm mein khol sakte hain. Roz ke kaam ke liye internet zaroori nahi; pehli dafa dependencies install karne ke liye chahiye.

1. Windows par Python **3.12 (64-bit)** install karein; Python Launcher bhi enable karein.
2. Project folder mein `setup_windows.bat` chalaein. Installation complete hone dein.
3. `run_windows.bat` se app khol lein. PyCharm mein isi folder ko Open karke interpreter `.venv\Scripts\python.exe` select karein aur `main.py` Run karein.
4. Pehli baar academy ki details aur apna owner account banayein. Password kam az kam 10 characters ka ho. Koi default password nahi hai.
5. Recovery code save kar lein. Isay computer aur database se alag mehfooz rakhein.

## Academy ka kaam

- **Staff access:** staff signup ke baad pending rahega. Owner usay approve karke receptionist, cashier ya teacher banayega.
- **Admissions:** pehle class/batch banayein; phir New admission mein student aur guardian ki details dein. Save karte hi student ID aur pehla challan ban jayega.
- **Fee ledger:** challan select karein. Admin/cashier Receive payment se received amount enter karega. Kuch fee milne par Partially paid, poori milne par Paid ho jayega.
- **Collection register:** receipt select karke PDF save karein. PDF viewer se print karein, ya internet ho to apne email/WhatsApp se bhej dein.
- Ghalat payment ko owner reason ke saath reverse kar sakta hai. Purani entry history se delete nahi hoti.
- Agle mahine **Prepare challan** se naya bill banayein. Har student ke liye ek fee month mein ek challan banta hai.
- Teacher sirf apni assigned classes ki attendance mark karega.
- **Administration:** USB ya kisi alag drive par regular backup banayein. Restore se pehle current data ki safety copy bhi app khud banati hai.

Bank transfer/card payment ko cashier verify karke enter karega. Yeh offline app bank, JazzCash ya WhatsApp se automatic connect nahi hoti. Result cards, salaries/expenses aur student portal abhi is version mein shamil nahi hain.

Windows `.exe` banane aur backup/data location ki tafseel [README.md](README.md) mein hai. Windows executable ko academy ke computer par build/test karna hoga; cloud mein source app aur tests verify kiye gaye hain.
