import os
import re

prefabs_dir = r"d:\AIML\Projects\Major\MangaluruDigitalTwin3D\Assets\Resources\Cars"

for filename in os.listdir(prefabs_dir):
    if filename.endswith(".prefab"):
        path = os.path.join(prefabs_dir, filename)
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
            
        # Find all MonoBehaviour sections
        mb_pattern = re.compile(r'--- !u!114 &(\d+)\s+MonoBehaviour:.*?(?=--- !u!|\Z)', re.DOTALL)
        
        matches = mb_pattern.findall(content)
        new_content = content
        
        for mb_id in matches:
            # Remove the reference
            ref_pattern = re.compile(r'\s*- component: \{fileID: ' + mb_id + r'\}')
            new_content = ref_pattern.sub('', new_content)
            
            # Remove the whole MonoBehaviour block
            block_pattern = re.compile(r'--- !u!114 &' + mb_id + r'\s+MonoBehaviour:.*?(?=--- !u!|\Z)', re.DOTALL)
            new_content = block_pattern.sub('', new_content)
            
        with open(path, "w", encoding="utf-8") as f:
            f.write(new_content)
            
        print(f"Cleaned {filename}, removed {len(matches)} dummy scripts.")
