
Find named entities using [spaCy]([url](https://github.com/explosion/spaCy)), save them to a csv file. Then use that csv to find and replace named entities with placeholders. Only works with text. This is not a security tool. 

It is useful however for doing things like removing the names of people before pasting something into chatGPT, etc. 

It is called Qtanon because the GUI is made with [Qt]([url](https://en.wikipedia.org/wiki/Qt_(software))) and I am very funny. 

To run download the python script and
```
python Qtanon.py
```
On first run it downloads the spaCy en_core_web_lg, which is about 400 mb. You can specify using a smaller model, but it's fast enough that performance shouldn't be an issue. 

fake-plates.py is the same thing but via command line. 

![image](https://github.com/user-attachments/assets/f064c0ac-dbc2-427e-8133-e34859298a1d)

MIT lisence, except for the contents of /test-examples, which are used under a CC lisence from ProPublica and the Connecticut Mirror. 

