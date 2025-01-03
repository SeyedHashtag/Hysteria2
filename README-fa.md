<div dir="rtl">

# اسکریپت مدیریت Hysteria2

این اسکریپت یک رابط کاربری جامع مبتنی بر منو را برای مدیریت سرور Hysteria2، حساب‌های کاربری و خدمات مختلف فراهم می‌کند.

این اسکریپت از نصب، مدیریت کاربران، نظارت بر ترافیک و ادغام با ابزارهای اضافی مانند وارپ ، ساب لینک سینگ باکس و ربات تلگرام پشتیبانی می‌کند.

### دستور نصب:
```shell
bash <(curl https://raw.githubusercontent.com/SeyedHashtag/Hysteria2/main/install.sh)
```
پس از نصب، فقط از دستور `hys2` برای اجرای اسکریپت Hysteria2 استفاده کنید.

نیازی به اجرای مجدد دستور نصب نیست.

### دستور ارتقاء:
```shell
bash <(curl https://raw.githubusercontent.com/SeyedHashtag/Hysteria2/main/upgrade.sh)
```

<br />
<p align="center">
<img src="https://github.com/user-attachments/assets/57e544cb-7456-4fe7-adea-e9dd17a7c83b" width="600" height="300">
<p/>

## ویژگی‌ها:

**نصب و پیکربندی Hysteria2:**

  - نصب و پیکربندی Hysteria2 روی سرور خود.
  - مدیریت حساب‌های کاربری (افزودن، ویرایش، بازنشانی، حذف، لیست).
  - نظارت بر ترافیک و نمایش URIهای کاربر.

**گزینه‌های پیشرفته:**

  - نصب و مدیریت خدمات اضافی مانند WARP و TCP Brutal.
  - شروع/توقف خدمات Singbox SubLink و ربات تلگرام.
  - تغییر شماره پورت برای Hysteria2.
  - به‌روزرسانی یا حذف نصب Hysteria2.

**منوهای تعاملی:**

  - رابط کاربری مبتنی بر منو برای راحتی در جابجایی و مدیریت.
  - اعتبارسنجی برای ورودی‌های کاربر و بررسی‌های سیستمی برای جلوگیری از پیکربندی‌های نادرست.

## منوی اصلی:
  
- **نصب و پیکربندی Hysteria2:** پیکربندی Hysteria2 با تنظیمات مورد نظر.
- **افزودن کاربر:** افزودن کاربر جدید با محدودیت‌های ترافیکی و روزهای انقضا.
- **ویرایش کاربر:** تغییر جزئیات کاربر مانند نام کاربری، محدودیت ترافیک، روزهای انقضا، رمز عبور و غیره.
- **بازنشانی کاربر:** بازنشانی آمار کاربر.
- **حذف کاربر:** حذف کاربر از سیستم.
- **دریافت کاربر:** بازیابی اطلاعات دقیق کاربر خاص.
- **لیست کاربران:** نمایش لیستی از تمام کاربران.
- **بررسی وضعیت ترافیک:** مشاهده وضعیت فعلی ترافیک.
- **نمایش URI کاربر:** تولید و نمایش URI برای یک کاربر.

## منوی پیشرفته:

   - **نصب TCP Brutal:** نصب سرویس TCP Brutal.
  - **نصب WARP:** نصب سرویس WARP از Cloudflare.
  - **پیکربندی WARP:** پیکربندی WARP برای مسیرهای ترافیکی مختلف.
  - **حذف WARP:** حذف WARP از سیستم.
  - **ربات تلگرام:** شروع یا توقف سرویس ربات تلگرام.
  - **ساب لینک سینگباکس:** شروع یا توقف سرویس Singbox.
  - **تغییر پورت Hysteria2:** تغییر پورتی که Hysteria2 به آن گوش می‌دهد.
  - **به‌روزرسانی Hysteria2:** به‌روزرسانی Hysteria2 به نسخه جدیدترین.
  - **حذف نصب Hysteria2:** حذف Hysteria2 و پیکربندی‌های آن.

## پیش‌نیازها:
اطمینان حاصل کنید که بسته‌های زیر نصب شده‌اند:

- توزیع لینوکس مبتنی بر اوبونتو (تست شده بر روی اوبونتو 22)
- jq
- qrencode
- curl
- pwgen
- uuid-runtime

اگر هر یک از این موارد وجود نداشته باشد، اسکریپت سعی خواهد کرد آنها را به طور خودکار نصب کند.


## ملاحظه:

این اسکریپت تنها برای مقاصد آموزشی ارائه شده است. توسعه‌دهندگان هیچ مسئولیتی در قبال سوءاستفاده یا پیامدهای ناشی از استفاده از آن ندارند. لطفاً قبل از استقرار در محیط تولید، مطمئن شوید که پیامدهای استفاده از Hysteria2 و ابزارهای مرتبط را درک کرده‌اید.
