# Translating Tencent's WeChat Developer Tools
A quick and dirty script to translate the [WeChat Developer Tools](https://mp.weixin.qq.com/debug/wxadoc/dev/devtools/download.html) into English (or any other language)

![Splash screen](img/splash.png?raw=true "English WeChat Developer Tools")
![Main screen](img/main.png?raw=true "English WeChat Developer Tools")


# Download

## package.nw
Extract the `package.nw` directory and merge it with the one in the WeChat DevTools installation directory.

* [1.01.170913](releases/package.nw.1.01.170913.zip)

## Pre-translated Entire Installation 
Extract and run the executable.

* [windows64 - 1.01.170913](releases/win64_1.01.170913.zip)

# Run the Translation script yourself

## How to use

* Set the permissions so that you are able to write to the `package.nw` directory within the WeChat Developer Tools installation directory.

* Make sure you have Python 3 installed

* [Optional] Get a Google Cloud API Key if you don't want to use the translations in `translations.json`

## Windows 
`python generate.py --nwdir="c:\program files\tencent\devtools\package.nw" --key=apikey-from-google`
