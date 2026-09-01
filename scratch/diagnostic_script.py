import sys
import os

os.chdir(r'd:\AIML\Projects\Major\AI-Predictive-Traffic')
net_file = 'file:///D:/AIML/Projects/Major/AI-Predictive-Traffic/simulation/mangaluru/mangaluru.net.xml'
hospitals_file = 'simulation/mangaluru/presentation_labels.add.xml'

sys.path.append('controller')
from hospital_manager import HospitalManager

hm = HospitalManager(net_file, hospitals_file)
for hosp in hm.get_all_hospitals():
    print(f'[{hosp.id}] {hosp.name}: Nearest Edge = {hosp.nearest_edge}')
