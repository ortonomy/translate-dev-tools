#!/usr/bin/env python
# -*- coding: utf-8 -*-
#

from googleapiclient.discovery import build
import fnmatch
import json
import os
import glob
import shutil
import esprima
import argparse
import re



def fileSearchReplace(filepath, findStr, replaceStr):
    """Open a file and find/replace all matches"""
    with open(filepath, "r+", encoding="utf-8") as f:
        rawText = f.read()
        f.seek(0)
        f.write(rawText.replace(findStr, replaceStr))
        f.truncate()



def parseAsDict(filepath):
    """ Simple, naive parsing of a Javascript Object source file into a Dictionary

        Used for the locale-specific string collections
    """
    r = re.compile(r'\n\s*([^:]*):\s*([^\n]*)', re.UNICODE)
    with open(filepath, "r", encoding="utf-8") as f:
        rawText = f.read()           
        matches = r.findall(rawText)
        # convert to a dictionary
        result = {}
        for (kAttr, kValue) in matches:
            #get ride of spaces
            kValue = kValue.strip()
            # get rid of comma at end if exists
            if kValue[-1]==',':
                kValue=kValue[:-1].strip()
            # get rid of quote marks because the regex was a bit crap
            kValue = kValue[1:-1]
            #put in dictionary
            result[kAttr] = kValue
    return result



def saveDictAsJsObject(filepath, dictObj):
    """ Save a Dictionary object into a Javascript Object format

        Used for saving locale-specific string collections
    """
    with open(filepath, "w", encoding="utf-8") as f:
        f.write("module.exports = {\n")
        for (k,v) in dictObj.items():
            # process the quotation marks etc
            f.write(k+':\''+v+'\',\n')
        f.write("}")


class Translator(object):
    """Wrapper for the Google Translation API. Must provide your own API Key"""
    def __init__(self, apiKey):
        self.GOOGLE_CHUNKSIZE = 64
        self.apiKey = apiKey
        self.service = build('translate', 'v2', developerKey=apiKey)

    def encodeForTranslation(self, strValue):
        strValue = strValue.replace('%s', '<s-placeholder/>')
        strValue = strValue.replace('%d', '<d-placeholder/>')
        strValue = strValue.replace('%f', '<f-placeholder/>')
        strValue = strValue.replace('%i', '<i-placeholder/>')
        strValue = strValue.replace('%o', '<o-placeholder/>')
        strValue = strValue.replace('\n', '<nl-placeholder/>')
        return strValue

    def decodeFromTranslation(self, strValue):
        strValue = strValue.replace('<s-placeholder/>', '%s')
        strValue = strValue.replace('<d-placeholder/>', '%d')
        strValue = strValue.replace('<f-placeholder/>', '%f')
        strValue = strValue.replace('<i-placeholder/>', '%i')
        strValue = strValue.replace('<o-placeholder/>', '%o')
        strValue = strValue.replace('<nl-placeholder/>', '\n')
        strValue = strValue.replace('&#39;', '\\\'')
        return strValue

    def translate(self, chinesePhrase, newLanguage='en'):
        return self.translateList([chinesePhrase], newLanguage)

    def translateSmallList(self, chinesePhraseList, newLanguage='en'):
        # encode the strings
        chinesePhraseList = [self.encodeForTranslation(x) for x in chinesePhraseList]
        cloudresult = self.service.translations().list(source='zh', target=newLanguage, q=chinesePhraseList).execute()        
        # parse the result into a simple list                
        result = []
        for t in cloudresult['translations']:
            result.append(self.decodeFromTranslation(t['translatedText']))
        return result

    def translateList(self, chinesePhraseList, newLanguage='en'):
        # break it into smaller chunks and then join        
        translatedValues = []
        for x in range(0, len(chinesePhraseList)//self.GOOGLE_CHUNKSIZE):
            translatedValues += self.translateSmallList(list(chinesePhraseList[x*self.GOOGLE_CHUNKSIZE:(x+1)*self.GOOGLE_CHUNKSIZE]), newLanguage)        
        # the remainder
        translatedValues += self.translateSmallList(list(chinesePhraseList[len(translatedValues):]), newLanguage)        
        return translatedValues

class TranslationCache(object):
    """ Used for caching results of translations, so we don't repeatedly ask Google same questions """
    def __init__(self, filepath):
        self.filepath = filepath
        self.items = {}
        if os.path.exists(filepath):
            with open(filepath, 'r') as f:
                self.items = json.load(f)        

    def get(self, key):
        try:
            return self.items[key]
        except:
            return None

    def put(self, key, value):
        self.items[key] = value

    def save(self):
        with open(self.filepath, 'w') as f:
            json.dump(self.items, f)



class SourceRegion(object):
    """ Represent a region in the source code """
    def __init__(self, token, rawCode):
        self.value = token.value
        self.range = token.range
        self.rawCode = rawCode

    def trimLeft(self, amount):
        self.value = self.value[amount:]
        self.range[0] += amount

    def trimRight(self, amount):
        self.value = self.value[:-amount]
        self.range[1] -= amount

    def trim(self, amount):
        """ Trim amount from both sides """
        self.trimLeft(amount)
        self.trimRight(amount)

    def stripSuffix(self, suffix):
        if self.value[-len(suffix):]==suffix:
            self.trimRight(len(suffix))

    def stripPrefix(self, prefix):
        if self.value[:len(prefix)]==prefix:
            self.trimLeft(len(prefix))            

    def strip(self, prefix, suffix):
        self.stripPrefix(prefix)
        self.stripSuffix(suffix)

    def rawValue(self):
        return self.rawCode[self.range[0]:self.range[1]].encode("utf-8").decode("unicode-escape")

    def __repr__(self):
        return (self.rawValue(), self.range)

    def __str__(self):
        return str(self.__repr__())


class ParsedSourceFile(object):
    """ Wrapper for esprima ES parsing library """
    def __init__(self, filepath):
        with open(filepath, "r", encoding="utf-8") as f:        
            self.rawCode = f.read()
            self.ast = esprima.parseScript(self.rawCode, range=True, tokens=True) 
        self.stringLiterals = self.getStringLiterals()         
        self.transform = 0  

    def getStringLiterals(self):
        """ Return a list of all string literal values
            We include the newer ` Template ` strings too
        """
        result = []
        for t in self.ast.tokens:
            if t.type=="String":
                r = SourceRegion(t, self.rawCode)
                r.strip("'", "'")
                r.strip('"', '"')
                r.strip(' ', ' ')
                result.append(r)
            elif t.type=="Template":
                r = SourceRegion(t, self.rawCode)
                r.strip('`', '`')               
                r.stripSuffix("${") # ignore placeholder characters
                r.stripSuffix("}") 
                r.stripPrefix("}") 
                r.strip(' ', ' ')              
                result.append(r)
        return result

    def replaceValue(self, sourceRegion, value):
        beforeCode = self.rawCode[:sourceRegion.range[0]+self.transform]
        afterCode = self.rawCode[sourceRegion.range[1]+self.transform:]
        self.rawCode = beforeCode+value+afterCode
        # did we shrink or grow the whole code string ?
        self.transform += len(value)-(sourceRegion.range[1]-sourceRegion.range[0])

    def save(self, filepath):
        with open(filepath, "w", encoding="utf-8") as f:    
            f.write(self.rawCode)





def containsChineseCharacters(strToSearch):
    """ Naive detection of Chinese letters in a string """
    r = re.compile(r'[\u4e00-\u9fff]+|\\[uU][4-9][0-9a-fA-F]{3}', re.UNICODE)
    #r = re.compile(r'[\u4e00-\u9fff]', re.UNICODE)
    #r = re.compile(r'\\[uU][4-9][0-9a-fA-F]{3}', re.UNICODE)
    return r.search(strToSearch)!=None


def chineseRatio(strToEvaluate):
    """ Return the approximate ratio of Chinese characters in the string """
    if strToEvaluate=='':
        return 0
    r = re.compile(r'[\u4e00-\u9fff]+|\\[uU][4-9][0-9a-fA-F]{3}', re.UNICODE)
    #r = re.compile(r'\\[uU][4-9][0-9a-fA-F]{3}', re.UNICODE)
    res = r.sub('', strToEvaluate)
    return (len(strToEvaluate)-len(res))/len(strToEvaluate)


def listJsFilesWithChinese(rootpath):
    """ Build up a list of interesting files that we will process later. Does not recurse. """
    matches = []
    print("Enumerating code files with Chinese strings ...")
    for filepath in glob.glob(os.path.join(rootpath, '*.js')):
        with open(filepath, "r", encoding="utf-8") as f:
            if containsChineseCharacters(f.read()):
                matches.append(filepath)
    print("Found "+str(len(matches)))
    return matches




def translateDictionary(translationCache, translator, zhDict, newLanguage='en', threshold=0.3):
    translatedDict = {}
    toTranslate = []
    for (key, value) in zhDict.items():
        if isinstance(value, str) and chineseRatio(value)>threshold:
            if key.strip()=='' or value.strip()=='':
                continue
            # make sure it is mostly chinese
            if translationCache.get(zhDict[key])!=None:
                translatedDict[key] = translationCache.get(zhDict[key])
            else:
                # We will ask google to translate
                toTranslate.append((key, zhDict[key]))
        elif isinstance(value, dict):
            translatedDict[key] = translateDictionary(translationCache, translator, value, newLanguage, threshold)
        else:
            translatedDict[key] = value
    # Do we need to ask Google to translate some things ?
    if toTranslate!=[]:
        translated = translator.translateList([x[1] for x in toTranslate], newLanguage)
        if len(translated)!=len(toTranslate):
            raise Exception("translateList should return same size list as input!")
        # add to the dictionary
        for x in range(0, len(toTranslate)):
            translatedDict[toTranslate[x][0]] = translated[x]
            # add to the cache
            translationCache.put(toTranslate[x][1], translated[x])
        translationCache.save()
    return translatedDict




def changeHardcodedLocale(rootpath, newLanguage='en'):
    """Fix the hardcoded locale.
    The developers have started to think about locales. But they hardcoded 'zh' as the current one
    and didnt actually translate any of the strings yet. lets help them :P
    """
    fileSearchReplace(os.path.join(rootpath, 'js/common/locales/index.js'), "const defaultLocales = 'zh'", "const defaultLocales = '"+newLanguage+"'")    


def changeMonacoLanguage(rootpath, newLanguage='en'):
    """Change the interface language for the Monaco Editor. Blank is English by default"""
    if newLanguage.lower()=='en':
        newLanguage = ''  # blank means English
    fileSearchReplace(os.path.join(rootpath, 'html/editor.html'), 'zh-cn', newLanguage)
    fileSearchReplace(os.path.join(rootpath, 'html/editor-dev.html'), 'zh-cn', newLanguage)


def translatePackageJson(translationCache, translator, rootpath, newLanguage='en'):
    # Main package.json
    filepath = os.path.join(rootpath, 'package.json')
    with open(filepath, 'r', encoding="utf-8") as f:
        packageDict = json.load(f)    
    translatedDict = translateDictionary(translationCache, translator, packageDict, newLanguage)
    with open(filepath, 'w', encoding="utf-8") as f:
        json.dump(translatedDict, f)


def generateLocaleStrings(translationCache, translator, rootpath, newLanguage='en'):
    """ Generate the missing locale-specific string collection. """
    # ensure directories exist
    if not os.path.exists(os.path.join(rootpath, 'js/common/locales/'+newLanguage)):
        os.makedirs(os.path.join(rootpath, 'js/common/locales/'+newLanguage))
    # do the translation work for both dict objects
    zhDict = parseAsDict(os.path.join(rootpath, 'js/common/locales/zh/index.js'))
    translatedDict = translateDictionary(translationCache, translator, zhDict, newLanguage, 0)
    # save the new dictionaries as JS objects
    saveDictAsJsObject(os.path.join(rootpath, 'js/common/locales/'+newLanguage+'/index.js'), translatedDict)




def translateFile(translationCache, translator, filepath, newLanguage='en', threshold=0.3):
    parsedFile = ParsedSourceFile(filepath)
    # build subset of qualifying mostly Chinese strings
    literalsToTranslate = []
    for literal in parsedFile.stringLiterals:
        if chineseRatio(literal.rawValue()) > threshold:
            # do we already have a translation ?
            t = translationCache.get(literal.rawValue())
            if t!=None:
                parsedFile.replaceValue(literal, t)
            else:
                literalsToTranslate.append(literal)
    # translate them all
    if literalsToTranslate!=[]:
        translations = translator.translateList([x.rawValue() for x in literalsToTranslate], newLanguage)
        # should be same length!
        if len(translations)!=len(literalsToTranslate):
            raise("Didn't get expected number of translations")
        # make the replacements
        for x in range(0, len(literalsToTranslate)):
            # save the translation to the cache
            translationCache.put(literalsToTranslate[x].rawValue(), translations[x])
            parsedFile.replaceValue(literalsToTranslate[x], translations[x])
        translationCache.save()
    # save changes to file
    parsedFile.save(filepath)






def main(args):
    nwdir = args.nwdir

    translator = Translator(args.key)
    translationCache = TranslationCache('translations.json')
    # do it
    translatePackageJson(translationCache, translator, nwdir, 'en')
    changeHardcodedLocale(nwdir, 'en')
    changeMonacoLanguage(nwdir, 'en')
    generateLocaleStrings(translationCache, translator, nwdir, 'en')
    # fix the hardcoded chinese strings in the js/ directory
    for filepath in listJsFilesWithChinese(os.path.join(nwdir,'js/')):
        translateFile(translationCache, translator, filepath, 'en')
    # # # THe editor extension too
    translateFile(translationCache, translator, os.path.join(nwdir,'js/extensions/editor/index.js'), 'en')
    for filepath in listJsFilesWithChinese(os.path.join(nwdir,'js/extensions/editor/assets/api')):
        translateFile(translationCache, translator, filepath, 'en')





if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("--nwdir", help="Path to the 'package.nw' directory.")
    parser.add_argument("--key", help="Google Cloud API Key for use with the translation services")
    args = parser.parse_args()    
    main(args)

