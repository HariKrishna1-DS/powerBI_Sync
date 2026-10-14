Follow this order: SA Key → Google Sheets Enable → Spreadsheet → Save settings → Test connection.
1. Click SA Key in the application. Sign in to Google Cloud, then select your project at the top. To create one, choose New Project, enter a name, and click Create.
2. Open ☰ → IAM & Admin → Service Accounts → Create service account. Enter a name such as sheet-sync-bot, then click Done. Additional Google Cloud roles are optional for accessing a directly shared spreadsheet. Google’s service-account instructions.
3. Click the new service account. Open Keys → Add key → Create new key, select JSON, and click Create. A .json file downloads to your computer—keep it private. Google’s key instructions.
4. Return to the application and click Google Sheets Enable. Confirm that the selected Cloud project is the same project that created your JSON key, then click Enable. If it shows Manage, the API is already enabled. Google’s API setup instructions.
5. Click Spreadsheet in the application. Create a Blank spreadsheet or open an existing spreadsheet you own. Give it any name you prefer.
6. In the application’s settings, click Import key or Replace key and select the downloaded .json file. The service-account email will appear below it.
7. Copy that service-account email. In Google Sheets, click Share, paste the email, select Editor, uncheck Notify people, and click Share. General access can remain Restricted. Google’s spreadsheet-sharing instructions.
8. Copy the spreadsheet’s full URL from your browser’s address bar. Paste it into Spreadsheet URL or ID in the application.
9. Keep the default Full Title tracker tab and Remaining Products tracker tab names for a new spreadsheet. If you already have tracker tabs, enter their exact names.
10. Click Save settings. After the workspace reopens, open settings again and click Test saved Google Sheets connection.
Once the connection test succeeds, click Sync to Sheets to upload your saved preview.
