import pprint
from datetime import datetime

from config import load_publishers, RAW_RSS_DIR
from sources.rss import RSSProcessor


publishers = load_publishers() # 加载数据源测试

rsspro = RSSProcessor() # 初始化 RSS 抓取器

for journal in publishers:
    print("=" * 50)
    print(journal["name"])
    try:        
        RAW_RSS_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d")
        rss_file_save_path = RAW_RSS_DIR / f"{journal["id"]}_{timestamp}.xml"

        if rss_file_save_path.exists():
            xml_text = rss_file_save_path.read_text()
        else:
            xml_text = rsspro.fetch_rss(journal["rss"])
            rsspro.save_raw_rss(xml_text, str(rss_file_save_path)) # 保存测试
        
        papers = rsspro.parse_rss(xml_text, journal) # 解析测试

        print(f"Found {len(papers)} papers")
        pprint.pprint(papers[0])
    
    except Exception as e:
        print("ERROR:", e)

"""
==================================================
Nature
Found 75 papers
{'doi': '10.1038/d41586-026-01504-w',
 'journal': 'Nature',
 'link': 'https://www.nature.com/articles/d41586-026-01504-w',
 'publisher': 'nature',
 'rss_fetched_at': '2026-05-16T20:24:39.808795',
 'title': 'Even mild blows to the head disrupt the microbiome',
 'updated': '2026-05-15'}
==================================================
Nature Physics
Found 8 papers
{'doi': '10.1038/s41567-026-03313-4',
 'journal': 'Nature Physics',
 'link': 'https://www.nature.com/articles/s41567-026-03313-4',
 'publisher': 'nature',
 'rss_fetched_at': '2026-05-16T20:24:40.559495',
 'title': 'Precision meets portability',
 'updated': '2026-05-15'}
==================================================
Nature Photonics
Found 8 papers
{'doi': '10.1038/s41566-026-01909-z',
 'journal': 'Nature Photonics',
 'link': 'https://www.nature.com/articles/s41566-026-01909-z',
 'publisher': 'nature',
 'rss_fetched_at': '2026-05-16T20:24:41.351520',
 'title': 'Ultrasensitive biosensing by radiative <i>Q</i>-factor modulation '
          'in strongly coupled three-dimensional bound-state-in-the-continuum '
          'metasurfaces',
 'updated': '2026-05-13'}
==================================================
Nature Communications
Found 8 papers
{'doi': '10.1038/s41467-026-72870-2',
 'journal': 'Nature Communications',
 'link': 'https://www.nature.com/articles/s41467-026-72870-2',
 'publisher': 'nature',
 'rss_fetched_at': '2026-05-16T20:24:42.164180',
 'title': 'Catalytic Markovnikov hydrophosphorylation of unactivated olefins '
          'via a radical-polar crossover rearrangement',
 'updated': '2026-05-16'}
==================================================
Science
Found 14 papers
{'doi': '10.1126/science.aea1260',
 'journal': 'Science',
 'link': 'https://www.science.org/doi/abs/10.1126/science.aea1260?af=R',
 'publisher': 'science',
 'rss_fetched_at': '2026-05-16T20:24:42.539804',
 'title': 'Mucosal vaccination in mice provides protection from diverse '
          'respiratory threats',
 'updated': '2026-02-19'}
==================================================
Science Advances
Found 73 papers
{'doi': '10.1126/sciadv.adx7966',
 'journal': 'Science Advances',
 'link': 'https://www.science.org/doi/abs/10.1126/sciadv.adx7966?af=R',
 'publisher': 'science',
 'rss_fetched_at': '2026-05-16T20:24:43.765974',
 'title': 'Glycerol-mediated nose-to-brain codelivery of anti–IL-17 and '
          'anti-CD73 antibodies enhances immunotherapy for melanoma brain '
          'metastases',
 'updated': '2026-05-13'}
==================================================
Physical Review Letters (Editors' suggestions)
Found 100 papers
{'doi': '10.1103/gmkp-bxf2',
 'journal': "Physical Review Letters (Editors' suggestions)",
 'link': 'http://link.aps.org/doi/10.1103/gmkp-bxf2',
 'publisher': 'aps',
 'rss_fetched_at': '2026-05-16T20:24:44.596736',
 'title': 'Spinless and Spinful Charge Excitations in Moiré Fractional Chern '
          'Insulators',
 'updated': '2026-05-14'}
==================================================
Physical Review Letters (Plasma and Solar Physics, Accelerators and Beams)
Found 100 papers
{'doi': '10.1103/3743-3h2l',
 'journal': 'Physical Review Letters (Plasma and Solar Physics, Accelerators '
            'and Beams)',
 'link': 'http://link.aps.org/doi/10.1103/3743-3h2l',
 'publisher': 'aps',
 'rss_fetched_at': '2026-05-16T20:24:45.418376',
 'title': 'Background-Free Intensity Autocorrelation for Femtosecond X-Ray '
          'Pulses',
 'updated': '2026-05-12'}
==================================================
Physical Review Accelerators and Beams (Editors' suggestions)
Found 100 papers
{'doi': '10.1103/rhdk-191j',
 'journal': "Physical Review Accelerators and Beams (Editors' suggestions)",
 'link': 'http://link.aps.org/doi/10.1103/rhdk-191j',
 'publisher': 'aps',
 'rss_fetched_at': '2026-05-16T20:24:46.259027',
 'title': 'Space-charge effects during half-integer resonance crossing in the '
          'CERN Proton Synchrotron Booster',
 'updated': '2026-05-12'}
==================================================
Physical Review Accelerators and Beams
Found 100 papers
{'doi': '10.1103/1kpk-757b',
 'journal': 'Physical Review Accelerators and Beams',
 'link': 'http://link.aps.org/doi/10.1103/1kpk-757b',
 'publisher': 'aps',
 'rss_fetched_at': '2026-05-16T20:24:47.122670',
 'title': 'Mitigation of transverse single-bunch instabilities with '
          'longitudinal impedance, feedback, and chromaticity',
 'updated': '2026-05-15'}
==================================================
Physical Review E (Plasma physics)
Found 100 papers
{'doi': '10.1103/jfw8-rv8g',
 'journal': 'Physical Review E (Plasma physics)',
 'link': 'http://link.aps.org/doi/10.1103/jfw8-rv8g',
 'publisher': 'aps',
 'rss_fetched_at': '2026-05-16T20:24:47.926510',
 'title': 'Fluid simulation of Jeans instability in nonthermal dusty plasmas',
 'updated': '2026-05-15'}
==================================================
Physical Review Applied (Editors' suggestions)
Found 100 papers
{'doi': '10.1103/wd4d-qf28',
 'journal': "Physical Review Applied (Editors' suggestions)",
 'link': 'http://link.aps.org/doi/10.1103/wd4d-qf28',
 'publisher': 'aps',
 'rss_fetched_at': '2026-05-16T20:24:48.797220',
 'title': 'Vector magnetometry using cavity-enhanced microwave readout in '
          'nitrogen-vacancy-center diamond',
 'updated': '2026-05-15'}
==================================================
Physical Review Applied
Found 100 papers
{'doi': '10.1103/wd4d-qf28',
 'journal': 'Physical Review Applied',
 'link': 'http://link.aps.org/doi/10.1103/wd4d-qf28',
 'publisher': 'aps',
 'rss_fetched_at': '2026-05-16T20:24:49.622336',
 'title': 'Vector magnetometry using cavity-enhanced microwave readout in '
          'nitrogen-vacancy-center diamond',
 'updated': '2026-05-15'}
==================================================
High Power Laser Science and Engineering
Found 28 papers
{'doi': '10.1017/hpl.2025.10102',
 'journal': 'High Power Laser Science and Engineering',
 'link': 'https://dx.doi.org/10.1017/hpl.2025.10102?rft_dat=source%3Ddrss',
 'publisher': 'cambridge',
 'rss_fetched_at': '2026-05-16T20:24:50.143089',
 'title': 'High Power Laser Science and Engineering Editorial – a celebration '
          'of ultra-high-power lasers',
 'updated': '2026-02-13'}
==================================================
Physics of Plasmas (Current Issue)
Found 54 papers
{'doi': '10.1063/5.0325551',
 'journal': 'Physics of Plasmas (Current Issue)',
 'link': 'https://pubs.aip.org/aip/pop/article/33/5/052112/3391374/The-effects-of-dielectric-rods-on-streamer',
 'publisher': 'aip',
 'rss_fetched_at': '2026-05-16T20:24:50.958673',
 'title': 'The effects of dielectric rods on streamer dynamics in patterned '
          'dielectric barrier discharges',
 'updated': '2026-05-15'}
==================================================
Physics of Plasmas (Open Issue)
Found 1 papers
{'doi': '10.1063/5.0325551',
 'journal': 'Physics of Plasmas (Open Issue)',
 'link': 'https://pubs.aip.org/aip/pop/article/33/5/052112/3391374/The-effects-of-dielectric-rods-on-streamer',
 'publisher': 'aip',
 'rss_fetched_at': '2026-05-16T20:24:51.367842',
 'title': 'The effects of dielectric rods on streamer dynamics in patterned '
          'dielectric barrier discharges',
 'updated': '2026-05-15'}
==================================================
Applied Physics Letters (Current Issue)
Found 61 papers
{'doi': '10.1063/5.0329318',
 'journal': 'Applied Physics Letters (Current Issue)',
 'link': 'https://pubs.aip.org/aip/apl/article/128/19/194001/3391238/A-cavity-mediated-reconfigurable-coupling-scheme',
 'publisher': 'aip',
 'rss_fetched_at': '2026-05-16T20:24:52.360556',
 'title': 'A cavity-mediated reconfigurable coupling scheme for '
          'superconducting qubits',
 'updated': '2026-05-14'}
==================================================
Applied Physics Letters (Open Issue)
Found 1 papers
{'doi': '10.1063/5.0329318',
 'journal': 'Applied Physics Letters (Open Issue)',
 'link': 'https://pubs.aip.org/aip/apl/article/128/19/194001/3391238/A-cavity-mediated-reconfigurable-coupling-scheme',
 'publisher': 'aip',
 'rss_fetched_at': '2026-05-16T20:24:52.755161',
 'title': 'A cavity-mediated reconfigurable coupling scheme for '
          'superconducting qubits',
 'updated': '2026-05-14'}
==================================================
Review of Scientific Instruments (Current Issue)
Found 44 papers
{'doi': '10.1063/5.0282528',
 'journal': 'Review of Scientific Instruments (Current Issue)',
 'link': 'https://pubs.aip.org/aip/rsi/article/97/5/055211/3391301/Numerical-and-experimental-measurements-of-torque',
 'publisher': 'aip',
 'rss_fetched_at': '2026-05-16T20:24:53.491434',
 'title': 'Numerical and experimental measurements of torque and temperature '
          'characteristics for a multi-disk magnetorheological fluid brake',
 'updated': '2026-05-15'}
==================================================
Review of Scientific Instruments (Open Issue)
Found 4 papers
{'doi': '10.1063/5.0282528',
 'journal': 'Review of Scientific Instruments (Open Issue)',
 'link': 'https://pubs.aip.org/aip/rsi/article/97/5/055211/3391301/Numerical-and-experimental-measurements-of-torque',
 'publisher': 'aip',
 'rss_fetched_at': '2026-05-16T20:24:53.909036',
 'title': 'Numerical and experimental measurements of torque and temperature '
          'characteristics for a multi-disk magnetorheological fluid brake',
 'updated': '2026-05-15'}
==================================================
Plasma Physics and Controlled Fusion
Found 10 papers
{'doi': '10.1088/1361-6587/ae67a2',
 'journal': 'Plasma Physics and Controlled Fusion',
 'link': 'https://iopscience.iop.org/article/10.1088/1361-6587/ae67a2',
 'publisher': 'iop',
 'rss_fetched_at': '2026-05-16T20:24:55.072279',
 'title': 'Divertor detachment and heat exhaust mitigation control in KSTAR '
          'with tungsten divertor',
 'updated': '2026-05-15'}
==================================================
Optica
Found 19 papers
{'doi': '10.1364/OPTICA.587491',
 'journal': 'Optica',
 'link': 'https://opg.optica.org/abstract.cfm?URI=optica-13-5-951',
 'publisher': 'optica',
 'rss_fetched_at': '2026-05-16T20:24:56.068352',
 'title': 'On-demand holographic VCSELs with integrated nanoprinted '
          'diffractive neural networks',
 'updated': '2026-05-20'}
==================================================
Optics Express
Found 137 papers
{'doi': '10.1364/OE.581443',
 'journal': 'Optics Express',
 'link': 'https://opg.optica.org/abstract.cfm?URI=oe-34-10-19109',
 'publisher': 'optica',
 'rss_fetched_at': '2026-05-16T20:24:57.438504',
 'title': 'High-precision vibration measurement in multilayer structures using '
          'low-coherence two-wave mixing interferometry',
 'updated': '2026-05-18'}
"""