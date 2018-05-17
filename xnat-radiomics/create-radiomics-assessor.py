
'''create-radiomics-assessor.py
Read in the metlab timecourse XML and create a radm:radiomics assessor XML for the given parent session

Usage:
    create-radiomics-assessor.py [--no-verify] XNAT_HOST XNAT_USER XNAT_PASS PROJECT SESSION_ID SESSION_LABEL METLAB_XML RADIOMICS_ASSESSOR_XML_DIR
    create-radiomics-assessor.py (-h | --help)
    create-radiomics-assessor.py --version

Options:
    XNAT_HOST                   XNAT server URL
    XNAT_USER                   A username or user alias token for XNAT server
    XNAT_PASS                   A password or password alias token for XNAT server
    PROJECT                     Project in which parent session and assessor live
    SESSION_ID                  XNAT Accession number of parent session
    SESSION_LABEL               Label of parent session
    METLAB_XML                  Input XML produced from matlab script
    RADIOMICS_ASSESSOR_XML_DIR  Directory in which to write output radm:radiomics assessor XML
    -h --help                   Show the usage
    --version                   Show the version
    --no-verify                 Do not verify server SSL certificate. (Useful for dev servers.)
'''

import os
import sys
import requests
import datetime as dt
from docopt import docopt
from lxml.builder import ElementMaker
from lxml.etree import tostring as xmltostring

def getValueFromBetweenTags(line):
    firstRightAngleBracket = line.find('>')
    secondLeftAngleBracket = line.find('<', firstRightAngleBracket)
    return line[firstRightAngleBracket+1:secondLeftAngleBracket]

def getValueOfAttribute(attrib, line):
    attribStartIdx = line.find(attrib + '="')
    attribValueStartIdx = attribStartIdx + len(attrib) + 2
    attribValueEndIdx = line.find('"', attribValueStartIdx)
    return line[attribValueStartIdx:attribValueEndIdx]

version = "1.0"
args = docopt(__doc__, version=version)

xnat_host = args.get('XNAT_HOST')
xnat_user = args.get('XNAT_USER')
xnat_pass = args.get('XNAT_PASS')
project = args.get('PROJECT')
session_id = args.get('SESSION_ID')
session_label = args.get('SESSION_LABEL')
metlabPath = args.get('METLAB_XML')
assessorXmlDir = args.get('RADIOMICS_ASSESSOR_XML_DIR')
verify = not args.get('--no-verify', True)

# These hold the mapping from metlab xml names to radiomics assessor names
metlabToRadiomicsShape = {
    'ml:vol_mm3'    : 'volume',
    'ml:shrt_d_mm'  : 'minorAxis',
    'ml:lng_d_mm'   : 'majorAxis',
    'ml:eccntrcty'  : 'elongation',
    'ml:sphrcty'    : 'sphericity'
}
metlabToRadiomicsFirstorder = {
    'ml:min'        : 'minimum',
    'ml:med'        : 'median',
    'ml:max'        : 'maximum',
    'ml:stddev'     : 'standardDeviation',
    'ml:entropy'    : 'entropy',
}

# This is the order in which elements must appear in radiomics assessor
firstorderElems = ['entropy', 'minimum', 'maximum', 'median', 'standardDeviation']
shapeElems = ['volume', 'sphericity', 'majorAxis', 'minorAxis', 'elongation']

nsdict = {'xnat': 'http://nrg.wustl.edu/xnat',
          'radm': 'http://nrg.wustl.edu/radm',
          'xsi': 'http://www.w3.org/2001/XMLSchema-instance'}

schema_location_template = "{0} {1}/xapi/schemas/{2}/{2}.xsd"
schema_location = " ".join(schema_location_template.format(nsdict[ns], xnat_host, ns) for ns in ('xnat', 'radm'))

def ns(namespace,tag):
    return "{%s}%s"%(nsdict[namespace], tag)

print("Verifying successful connection to XNAT server")
s = requests.Session()
s.verify = verify
s.auth = (xnat_user, xnat_pass)
r = s.get(xnat_host + '/data/JSESSION')
if not r.ok:
    sys.exit("Could not connect to XNAT server {}".format(xnat_host))
print("OK\n")

print("Reading metlab XML file {}".format(metlabPath))
with open(metlabPath, 'r') as f:
    metlab_xml = f.readlines()

print("Parsing values out of metlab XML structure.")

lesionInfo = {}
sessionInfo = {}
for line in metlab_xml:
    if 'ml:mets' in line:
        continue
    if 'ml:timepoints' in line:
        continue
    if '<ml:met' in line:
        # This is the start of a new lesion.
        currentLesion = line.split('"')[1]
        lesionInfo[currentLesion]= {}
        continue
    if '<ml:timepoint' in line:
        # This is the start of a new session "timecourse".
        currentSession = getValueOfAttribute("session", line)
        if currentSession not in sessionInfo:
            scan = getValueOfAttribute("scan", line)
            sessionInfo[currentSession] = {"scan": scan, "lesions": {}}
        sessionInfo[currentSession]['lesions'][currentLesion] = {}
    for tag, name in metlabToRadiomicsShape.iteritems():
        if tag in line:
            lesionInfo[currentLesion][name] = getValueFromBetweenTags(line)
            continue
    for tag, name in metlabToRadiomicsFirstorder.iteritems():
        if tag in line:
            sessionInfo[currentSession]['lesions'][currentLesion][name] = getValueFromBetweenTags(line)
            continue
print("Done.\n")
# print("lesionInfo")
# for lesion, d in lesionInfo.iteritems():
#     print(lesion)
#     for name, value in d.iteritems():
#         print("\t{}: {}".format(name, value))
# print("sessionInfo")
# for session, sessionDict in sessionInfo.iteritems():
#     print(session)
#     print("\tscan: {}".format(sessionDict['scan']))
#     for lesion, d in sessionDict['lesions'].iteritems():
#         print("\t" + lesion)
#         for name, value in d.iteritems():
#             print("\t\t{}: {}".format(name, value))
#

print("Creating lesion assessors for session {}".format(session_label))

assessor_template = "{}_{}_{}_{}"

sessionDict = sessionInfo[session_label]
scan = sessionDict['scan']

for lesion, firstorder in sessionDict['lesions'].iteritems():
    datestamp = dt.datetime.today().strftime('%Y%m%d%H%M%S')
    assessor_id = assessor_template.format(session_id, scan, lesion, datestamp)
    assessor_label = assessor_template.format(session_label, scan, lesion, datestamp)

    shape = lesionInfo[lesion]

    print("Constructing assessor XML\n\tlesion={}\n\tID={}\n\tlabel={}".format(lesion, assessor_id, assessor_label))

    assessorTitleAttributesDict = {
        'ID': assessor_id,
        'label': assessor_label,
        'project': project,
        ns('xsi','schemaLocation'): schema_location
    }

    E = ElementMaker(namespace=nsdict['radm'], nsmap=nsdict)
    assessorXML = E('Radiomics', assessorTitleAttributesDict,
        E(ns('xnat', 'date'), dt.date.today().isoformat()),
        E(ns('xnat', 'imageSession_ID'), session_id),
        E('firstorder',
            *[E(name, firstorder[name]) for name in firstorderElems]
        ),
        E('shape',
            *[E(name, shape[name]) for name in shapeElems]
        )
    )

    print("Creating assessor on server {}".format(xnat_host))
    r = s.put(xnat_host + '/data/projects/{}/experiments/{}/assessors/{}')
    xmltostring(assessorXML, pretty_print=True, encoding='UTF-8', xml_declaration=True)

