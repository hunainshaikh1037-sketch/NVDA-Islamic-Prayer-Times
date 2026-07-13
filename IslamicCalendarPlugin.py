import globalPluginHandler
import ui
import threading
import time
import os
from datetime import datetime, timedelta
import gui
import wx
import addonHandler
import winsound
import config
import urllib.request
import json

# Addon details initialization
addonHandler.initTranslation()

# Pre-defined database for Countries and Cities (Fallback if API is offline)
PRAYER_DATABASE = {
	"Pakistan": {
		"Karachi": {"fajr": "05:00", "zohr": "12:30", "asr": "16:45", "maghrib": "19:15", "isha": "20:45"},
		"Lahore": {"fajr": "04:45", "zohr": "12:15", "asr": "16:30", "maghrib": "19:05", "isha": "20:35"},
		"Islamabad": {"fajr": "04:40", "zohr": "12:15", "asr": "16:35", "maghrib": "19:10", "isha": "20:45"},
		"Multan": {"fajr": "05:05", "zohr": "12:25", "asr": "16:45", "maghrib": "19:15", "isha": "20:40"}
	},
	"India": {
		"Mumbai": {"fajr": "05:15", "zohr": "12:40", "asr": "17:00", "maghrib": "19:15", "isha": "20:35"},
		"Delhi": {"fajr": "04:30", "zohr": "12:20", "asr": "16:40", "maghrib": "19:15", "isha": "20:45"}
	}
}

FIQH_MODES = ["Hanafi", "Shafi'i", "Maliki", "Hanbali", "Jafari (Shia)"]

ISLAMIC_MONTHS = [
	"Muharram", "Safar", "Rabi-ul-Awwal", "Rabi-ul-Thani",
	"Jumada-al-Awwal", "Jumada-al-Thani", "Rajab", "Shaban",
	"Ramadan", "Shawwal", "Dhu-al-Qadah", "Dhu-al-Hijjah"
]

ISLAMIC_EVENTS = {
	("Muharram", 1): "New Islamic Year (1st Muharram)",
	("Muharram", 9): "Yaum-e-Ashoora Eve (9th Muharram)",
	("Muharram", 10): "Yaum-e-Ashoora (10th Muharram)",
	("Rabi-ul-Awwal", 12): "Eid Milad-un-Nabi (12th Rabi-ul-Awwal)",
	("Rajab", 27): "Shab-e-Meraj (27th Rajab)",
	("Shaban", 15): "Shab-e-Barat (15th Shaban)",
	("Ramadan", 1): "First Day of Ramadan Moobarak!",
	("Ramadan", 21): "Shahadat Imam Ali (21st Ramadan)",
	("Ramadan", 27): "Shab-e-Qadr (27th Ramadan Night)",
	("Shawwal", 1): "Eid-ul-Fitr (1st Shawwal)",
	("Dhu-al-Hijjah", 1): "1st Dhu-al-Hijjah (Hajj season begins)",
	("Dhu-al-Hijjah", 9): "Yaum-e-Arafah (9th Dhu-al-Hijjah)",
	("Dhu-al-Hijjah", 10): "Eid-ul-Adha (10th Dhu-al-Hijjah)"
}

def get_islamic_date(country, city, manual_offset=0, prayers_dict=None):
	"""Kuwaiti Algorithm modification to estimate Hijri date with precise Maghrib transition"""
	today = datetime.now()
	
	maghrib_time_str = "19:00"
	if prayers_dict and "maghrib" in prayers_dict:
		maghrib_time_str = prayers_dict["maghrib"]
	
	try:
		maghrib_time = datetime.strptime(maghrib_time_str, "%H:%M").time()
		if today.time() >= maghrib_time:
			today += timedelta(days=1)
	except ValueError:
		pass
		
	if manual_offset != 0:
		today += timedelta(days=manual_offset)

	year, month, day = today.year, today.month, today.day
	if month < 3:
		year -= 1
		month += 12
	A = int(year / 100)
	B = int(A / 4)
	C = 2 - A + B
	E = int(365.25 * (year + 4716))
	F = int(30.6001 * (month + 1))
	jd = C + day + E + F - 1524.5 + 0.5
	Z = int(jd)
	alpha = int((Z - 1867216.25) / 365.2425)
	A = Z + 1 + alpha - int(alpha / 4)
	B = A + 1524
	C = int((B - 122.1) / 365.25)
	D = int(365.25 * C)
	E = int((B - D) / 30.6001)
	my_jd = jd - 1948440 + 10632
	n = int((my_jd - 1) / 10631)
	my_jd = my_jd - 10631 * n + 354
	j = (int((10985 - my_jd) / 5316)) * (int((50 * my_jd) / 17719)) + (int(my_jd / 5670)) * (int((43 * my_jd) / 15238))
	my_jd = my_jd - (int((30 - j) / 15)) * (int((17719 * j) / 50)) - (int(j / 16)) * (int((15238 * j) / 43)) + 29
	hijri_month = int((24 * my_jd) / 709)
	hijri_day = my_jd - int((709 * hijri_month) / 24)
	hijri_year = 30 * n + j - 30
	if hijri_month > 12: hijri_month = 12
	if hijri_month < 1: hijri_month = 1
	return int(hijri_day), ISLAMIC_MONTHS[hijri_month - 1], int(hijri_year)

def check_special_day(day, month):
	return ISLAMIC_EVENTS.get((month, day), None)


class PrayerSettingsDialog(wx.Dialog):
	"""Upgraded Settings GUI Window with 5 Fiqhs"""
	def __init__(self, parent, plugin_instance):
		super(PrayerSettingsDialog, self).__init__(parent, title=_("Islamic Calendar & Prayer Settings"))
		self.plugin = plugin_instance
		mainSizer = wx.BoxSizer(wx.VERTICAL)
		
		wx.StaticText(self, label=_("Select Country:"))
		self.countryChoice = wx.Choice(self, choices=list(PRAYER_DATABASE.keys()))
		self.countryChoice.SetStringSelection(self.plugin.current_country)
		self.countryChoice.Bind(wx.EVT_CHOICE, self.onCountryChange)
		mainSizer.Add(self.countryChoice, 0, wx.ALL | wx.EXPAND, 5)
		
		wx.StaticText(self, label=_("Select City:"))
		current_cities = list(PRAYER_DATABASE.get(self.plugin.current_country, PRAYER_DATABASE["Pakistan"]).keys())
		self.cityChoice = wx.Choice(self, choices=current_cities)
		self.cityChoice.SetStringSelection(self.plugin.current_city)
		mainSizer.Add(self.cityChoice, 0, wx.ALL | wx.EXPAND, 5)
		
		wx.StaticText(self, label=_("Select Fiqh (Sect):"))
		self.fiqhChoice = wx.Choice(self, choices=FIQH_MODES)
		self.fiqhChoice.SetStringSelection(self.plugin.current_fiqh)
		mainSizer.Add(self.fiqhChoice, 0, wx.ALL | wx.EXPAND, 5)
		
		btnSizer = self.CreateButtonSizer(wx.OK | wx.CANCEL)
		if btnSizer: mainSizer.Add(btnSizer, 0, wx.ALIGN_CENTER | wx.ALL, 10)
		self.SetSizer(mainSizer)
		mainSizer.Fit(self)
		
	def onCountryChange(self, event):
		country = self.countryChoice.GetStringSelection()
		self.cityChoice.Clear()
		self.cityChoice.AppendItems(list(PRAYER_DATABASE[country].keys()))
		self.cityChoice.SetSelection(0)


class GlobalPlugin(globalPluginHandler.GlobalPlugin):
	"""Main NVDA Plugin Class"""
	
	__gestures = {
		"kb:NVDA+.": "announceIslamicDate",
		"kb:NVDA+shift+.": "checkNextPrayer",
		"kb:NVDA+shift+s": "stopAzanAudio",
		"kb:NVDA+shift+alt+d": "adjustHijriOffset"
	}

	def __init__(self):
		super(GlobalPlugin, self).__init__()
		
		if "islamic_prayer" not in config.conf:
			config.conf["islamic_prayer"] = {}
		
		self.current_country = config.conf["islamic_prayer"].get("country", "Pakistan")
		self.current_city = config.conf["islamic_prayer"].get("city", "Karachi")
		self.current_fiqh = config.conf["islamic_prayer"].get("fiqh", "Hanafi")
		self.manual_offset = int(config.conf["islamic_prayer"].get("offset", 0))
		
		self.addon_dir = os.path.dirname(__file__)
		self.azan_path = os.path.join(self.addon_dir, "azan.wav")
		
		self.active_prayers = PRAYER_DATABASE.get(self.current_country, {}).get(self.current_city, {}).copy()
		
		try:
			self._toolsMenuSubMenu = gui.mainFrame.sysTrayIcon.toolsMenu
			self.menuItem = self._toolsMenuSubMenu.Append(wx.ID_ANY, _("Islamic Calendar & Prayer Settings..."))
			gui.mainFrame.sysTrayIcon.Bind(wx.EVT_MENU, self.onSettingsMenu, self.menuItem)
		except AttributeError:
			pass
		
		self.is_running = True
		self.last_triggered_time = ""
		
		# Async Live Sync & Monitoring
		self.sync_live_timings()
		self.monitor_thread = threading.Thread(target=self.prayer_monitor_loop)
		self.monitor_thread.daemon = True
		self.monitor_thread.start()
		
	def sync_live_timings(self):
		"""Fetch automated precise global timings according to selected location and fiqh method"""
		def fetch():
			# Mapping custom choices to standard calculation methods
			method = "1" if self.current_fiqh == "Jafari (Shia)" else "2"
			school = "1" if self.current_fiqh == "Hanafi" else "0"
			
			url = f"https://api.aladhan.com/v1/timingsByCity?city={self.current_city}&country={self.current_country}&method={method}&school={school}"
			try:
				req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
				with urllib.request.urlopen(req, timeout=5) as response:
					data = json.loads(response.read().decode())
					if data["code"] == 200:
						timings = data["data"]["timings"]
						self.active_prayers["fajr"] = timings["Fajr"]
						self.active_prayers["zohr"] = timings["Dhuhr"]
						self.active_prayers["asr"] = timings["Asr"]
						self.active_prayers["maghrib"] = timings["Maghrib"]
						self.active_prayers["isha"] = timings["Isha"]
			except Exception:
				pass # Fallback to local default DB structure on offline networks safely
		threading.Thread(target=fetch, daemon=True).start()

	def script_announceIslamicDate(self, gesture):
		d, m, y = get_islamic_date(self.current_country, self.current_city, self.manual_offset, self.active_prayers)
		message = f"Islamic Date: {d} {m} {y} AH."
		
		special_event = check_special_day(d, m)
		if special_event:
			message += f" Today is an important day: {special_event}!"
		ui.message(message)

	def script_checkNextPrayer(self, gesture):
		now = datetime.now()
		now_time = datetime.strptime(now.strftime("%H:%M"), "%H:%M")
		
		upcoming_prayer = None
		min_diff = float('inf')

		# Step 1: Aaj ki baki reh jane wali namazein check karein
		for name, p_time in self.active_prayers.items():
			try:
				p_dt = datetime.strptime(p_time[:5], "%H:%M")
				diff = (p_dt - now_time).total_seconds() / 60
				if 0 < diff < min_diff:
					min_diff = diff
					upcoming_prayer = (name, p_time[:5], False)  # False yani aaj ki namaz
			except ValueError:
				continue
				
		# Step 2: Agar aaj mazeed koi namaz baki nahi (e.g. Isha ke baad), to agla marhala kal ki Fajr hai
		if not upcoming_prayer:
			fajr_time_str = self.active_prayers.get("fajr", "05:00")[:5]
			try:
				p_dt = datetime.strptime(fajr_time_str, "%H:%M")
				# Kal ki Fajr tak ka farq nikalne ke liye 24 hours (1440 minutes) add karein
				diff = ((p_dt - now_time).total_seconds() / 60) + 1440
				upcoming_prayer = ("fajr", fajr_time_str, True)  # True yani kal ki Fajr
				min_diff = diff
			except ValueError:
				pass

		if upcoming_prayer:
			name, p_time, is_tomorrow = upcoming_prayer
			hours = int(min_diff // 60)
			minutes = int(min_diff % 60)
			
			# Time formatting (Hours aur Minutes)
			time_str = ""
			if hours > 0:
				time_str += f"{hours} hours and "
			time_str += f"{minutes} minutes remaining"
			
			if is_tomorrow:
				# Chunkay Maghrib ho chuki hai, Islami date badal chuki hai. Nayi Islami date hasil karein
				d, m, y = get_islamic_date(self.current_country, self.current_city, self.manual_offset, self.active_prayers)
				ui.message(
					f"Next prayer is Fajr at {p_time}. {time_str}. "
					f"As Maghrib has passed, the Islamic date has already changed to {d} {m} {y} AH."
				)
			else:
				ui.message(f"Next prayer is {name.capitalize()} at {p_time}. {time_str} ({self.current_fiqh} Method).")
		else:
			ui.message("Prayer timings are currently unavailable.")

	def script_stopAzanAudio(self, gesture):
		"""Instantly kill sound buffer on request"""
		winsound.PlaySound(None, winsound.SND_PURGE)
		ui.message("Azan sound stopped instantly.")

	def script_adjustHijriOffset(self, gesture):
		self.manual_offset = self.manual_offset + 1 if self.manual_offset < 2 else -2
		config.conf["islamic_prayer"]["offset"] = self.manual_offset
		d, m, y = get_islamic_date(self.current_country, self.current_city, self.manual_offset, self.active_prayers)
		ui.message(f"Hijri offset shifted to {self.manual_offset}. Current adjusted date: {d} {m}.")

	def prayer_monitor_loop(self):
		while self.is_running:
			now = datetime.now()
			current_time_str = now.strftime("%H:%M")
			
			if current_time_str != self.last_triggered_time:
				for prayer_name, prayer_time in self.active_prayers.items():
					if current_time_str == prayer_time[:5]:
						self.last_triggered_time = current_time_str
						self.play_azan_alert(prayer_name)
						break
			time.sleep(20)

	def play_azan_alert(self, prayer_name):
		d, month, _ = get_islamic_date(self.current_country, self.current_city, self.manual_offset, self.active_prayers)
		
		if month == "Ramadan" and prayer_name == "fajr":
			ui.message("Sehar time ended! It is time for Fajr Azan.")
		elif month == "Ramadan" and prayer_name == "maghrib":
			ui.message("Iftar time! It is time for Maghrib Azan.")
		else:
			ui.message(f"It is time for {prayer_name.capitalize()} Azan according to {self.current_fiqh} fiqh.")
			
		if prayer_name in ["maghrib", "fajr"]:
			event = check_special_day(d, month)
			if event:
				ui.message(f"Important Reminder: Today is {event}")
		
		if os.path.exists(self.azan_path):
			winsound.PlaySound(self.azan_path, winsound.SND_FILENAME | winsound.SND_ASYNC)
		else:
			for _ in range(3):
				winsound.Beep(1000, 500)
				time.sleep(0.2)

	def onSettingsMenu(self, event):
		dlg = PrayerSettingsDialog(gui.mainFrame, self)
		if dlg.ShowModal() == wx.ID_OK:
			self.current_country = dlg.countryChoice.GetStringSelection()
			self.current_city = dlg.cityChoice.GetStringSelection()
			self.current_fiqh = dlg.fiqhChoice.GetStringSelection()
			
			config.conf["islamic_prayer"]["country"] = self.current_country
			config.conf["islamic_prayer"]["city"] = self.current_city
			config.conf["islamic_prayer"]["fiqh"] = self.current_fiqh
			
			self.active_prayers = PRAYER_DATABASE.get(self.current_country, {}).get(self.current_city, {}).copy()
			self.sync_live_timings()
			ui.message(f"Settings successfully updated for {self.current_city} under {self.current_fiqh} calculations.")
		dlg.Destroy()

	def terminate(self):
		self.is_running = False
		try:
			winsound.PlaySound(None, winsound.SND_PURGE)
			if hasattr(self, '_toolsMenuSubMenu') and hasattr(self, 'menuItem'):
				self._toolsMenuSubMenu.Remove(self.menuItem)
		except Exception:
			pass
		super(GlobalPlugin, self).terminate()