import os
import re

prefabs_dir = r"d:\AIML\Projects\Major\MangaluruDigitalTwin3D\Assets\Resources\Cars"

for filename in os.listdir(prefabs_dir):
    if filename.endswith(".prefab"):
        path = os.path.join(prefabs_dir, filename)
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
            
        # We need to find the MonoBehaviour fileID.
        # It looks like:
        # --- !u!114 &some_id
        # MonoBehaviour:
        #   m_Script: {fileID: 11500000, guid: 63b6f4cac3b409640a9f649dc7ffcd33, type: 3}
        
        # 1. Find the fileID of the MonoBehaviour
        mb_pattern = re.compile(r'--- !u!114 &(\d+)\s+MonoBehaviour:.*?m_Script: {fileID: 11500000, guid: 63b6f4cac3b409640a9f649dc7ffcd33, type: 3}.*?(?=--- !u!)', re.DOTALL)
        
        matches = mb_pattern.findall(content)
        
        if not matches:
            # Let's try matching without the fileID: 11500000 just in case
            mb_pattern = re.compile(r'--- !u!114 &(\d+)\s+MonoBehaviour:(?:(?!--- !u!).)*?guid: 63b6f4cac3b409640a9f649dc7ffcd33.*?(?=--- !u!|\Z)', re.DOTALL | re.MULTILINE)
            for m in mb_pattern.finditer(content):
                matches.append(m.group(1))
                
        if not matches:
            # Maybe it's missing entirely (already missing script)
            pass
            
        new_content = content
        
        # We need to remove the component reference from GameObject
        # - component: {fileID: 12345678}
        for mb_id in matches:
            # Remove the reference
            ref_pattern = re.compile(r'\s*- component: \{fileID: ' + mb_id + r'\}')
            new_content = ref_pattern.sub('', new_content)
            
            # Remove the whole MonoBehaviour block
            block_pattern = re.compile(r'--- !u!114 &' + mb_id + r'\s+MonoBehaviour:.*?(?=--- !u!|\Z)', re.DOTALL)
            new_content = block_pattern.sub('', new_content)
            
        # Also clean up any other missing script components
        # (Those might just say m_Script: {fileID: 0})
        
        with open(path, "w", encoding="utf-8") as f:
            f.write(new_content)
            
        print(f"Cleaned {filename}, removed {len(matches)} dummy scripts.")
