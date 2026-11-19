import os,re,sys
p=sys.argv[1]; d=os.path.join(os.path.dirname(p),"pages")
out=[]
for l in open(p):
    c=l.rstrip("\n").split(" | ")
    if len(c)==6 and c[4].strip()=="pending" and os.path.exists(os.path.join(d,c[5].rstrip(" |").strip())):
        c[4]="read"; l=" | ".join(c)+"\n"
    out.append(l)
open(p,"w").writelines(out)
