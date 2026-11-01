# Intellectual Nexus Academy v1.1 — shuru kaise karein

Yeh Python + PySide6 ki **offline desktop app** hai. Roz ke kaam ke liye internet zaroori nahi; pehli installation aur EXE build ke dependencies download karne ke liye chahiye.

## Windows aur PyCharm

1. **Python 3.12, 64-bit** install karein; **Python Launcher** enable ho. Terminal mein `py -3.12 --version` se check kar sakte hain.
2. GitHub se **Code → Download ZIP** karein aur poora project extract karein.
3. **`setup_windows.bat`** chalaein. Yeh **`.venv312`** banata hai aur pinned dependencies install karta hai. Purani Python 3.14 wali `.venv` ko delete ya use nahi karta.
4. **`run_windows.bat`** se app kholein. PyCharm mein project Open karke interpreter **`.venv312\Scripts\python.exe`** select karein aur `main.py` Run karein.
5. Pehli baar academy details aur apna owner account banayein. Password kam az kam 10 characters ho. Koi default username/password nahi hai.
6. Jo **`.nexus-key` password reset file** save karne ka option aaye, usay private USB ya doosri mehfooz jagah save karein.

Agar `.venv312` pehle se ghalat Python version par bani hui ho, setup usay badlega nahi. Us folder ka naam badal kar uski files sambhal lein, phir setup dobara chalaein. Sirf Python 3.12 install karne se purani virtual environment 3.12 mein convert nahi hoti.

## Academy ka kaam

- **Staff access:** signup ke baad staff pending rahega. Owner approve karke receptionist, cashier ya teacher role dega.
- **Admissions:** pehle class/batch aur uski fee banayein. Phir New admission mein student, guardian, fee aur due date check karke save karein. Student ID aur pehla challan saath bante hain.
- Fee waqai zero ho to **Fee-exempt / no charges** khud select karein. Status **No payment due** hoga, **Paid** nahi; payment ya receipt record nahi hogi. Positive fee aur koi payment na ho to **Unpaid** rahega.
- **Fee ledger:** admin/cashier **Receive payment** se asal received amount enter karega. Kuch fee milne par **Partially paid**, poori milne par **Paid** hoga.
- **Collection register:** receipt PDF save karein aur PDF viewer se print karein. Ghalat payment ko owner reason ke saath reverse kar sakta hai; purani entry history mein rahegi.
- Agle mahine **Prepare challan** se naya bill banayein. Har student ke liye ek fee month mein ek challan hai.
- Teacher sirf assigned classes ki attendance mark karega. Reports se collection/overdue fees dekhein aur CSV export karein.
- **Administration:** regular database backup kisi alag drive par banayein. Restore se pehle app current data ki safety copy bhi rakhti hai.

### Purana zero ya ghalat challan theek karna

Purane zero-total bill ka data delete nahi hota; ab woh **No payment due** dikhata hai. Usay select karke **Fee ledger → Amend challan** kholein, sahi fee/due date aur correction ka reason dein. Positive fee save karne par bina payment wala bill **Unpaid** hoga; audit mein pehle aur baad ke amounts rahenge.

Student profile ki monthly fee edit karne se **future challans ka default** badalta hai; pehle wala bill nahi. Us bill ko alag **Amend challan** se theek karein. Jis bill par kabhi payment record hui ho, chahe baad mein reverse bhi hui ho, uska amount amend nahi hota. Received payments chupke se rewrite nahi hotin.

## Password bhool jayein to

Sign-in par **Forgot password? → Reset password** kholein, apni **`.nexus-key`** file choose karein aur naya password dein. Wohi file agle password reset ke liye bhi kaam karegi. Koi code dikhane ya type karne ki zaroorat nahi; email reset service nahi hai. Staff apna password owner se reset karwaye.

**Purane owners:** update ke baad apne mojooda password se sign in karein. **Administration → Owner account → Save password reset file…** mein current password confirm karke ek file save kar lein. Nayi reset file successfully save karne par purani reset files invalid ho jati hain. Cancel ya failed save se purani file invalid nahi hoti. File private rakhein: jis ke paas yeh ho, woh owner password reset kar sakta hai.

## Naye controls

Sign-in aur main window maximized khulti hain. Sign-in par chhota loading transition, buttons par hover/press feedback, smooth scrolling aur page fade hain. Manual sign-out par confirmation aati hai.

- **Ctrl+K:** apne role ke mutabiq records search karein.
- **Ctrl+F:** current page ki search field par jayein, jahan available ho.
- **Ctrl+R:** current page refresh karein.

## EXE banana

Windows par **`build_windows.bat`** double-click karein. Yeh Python **3.12 ki `.venv312`** use karta hai, PyInstaller **6.12.0** install karta hai aur yeh single file banata hai:

```text
dist\Intellectual Nexus Academy.exe
```

Python 3.14 wali purani `.venv` se build na karein. Manual build commands [README.md](README.md) mein hain. Windows helpers, EXE packaging aur physical printing ko academy ke Windows computer par test karna hai; Linux cloud mein in Windows commands ko run karke verify nahi kiya gaya.

## Update par purana data kaise bachega

Pehle app se **database backup** banayein, phir app band karke nayi source files ya EXE replace karein. V1.1 database schema aur records ko preserve karta hai. Wohi data folder use karein; update ke liye dobara academy create ya records delete na karein.

Windows par records project/`.venv312`/EXE se alag yahan rehte hain:

```text
%LOCALAPPDATA%\IntellectualNexusAcademy\academy.sqlite3
```

Agar `--data-dir` se apna folder use kiya tha to update ke baad bhi wohi folder dein. **Database backup**, exported PDFs aur **`.nexus-key` reset file** alag cheezein hain. Purana database restore karein to us backup ke waqt wala password ya matching reset file chahiye hogi.

Bank transfer/card payment cashier verify karke enter karega. Yeh app bank, JazzCash, email ya WhatsApp se automatic connect nahi hoti. Result cards, salaries/expenses aur student portal is release mein shamil nahi hain.
