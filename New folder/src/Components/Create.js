import React, { useState } from "react";
import axios from 'axios'
import {useNavigate} from 'react-router-dom'

const Create = () => {

    const [name, setName] = useState('')
    const [email, setEmail] = useState('')

    const header = {'Access-Control-Allow-Origin':"*"}

    const history =useNavigate()

    const handleSubmit = (e) => {

        e.preventDefault();
        console.log('clicked');
        axios.post('https://6392220eb750c8d178d7be42.mockapi.io/crud',{
            
                name: name,
                email: email,
                header

        }).then(
            ()=>{
                history('/read')
            }
        )
    }


    return <div className="container">
        <h2>Create</h2>
        <form>
            <div className="mb-3">
                <label className="form-label">Name</label>
                <input type="text" className="form-control" onChange={(e) => setName(e.target.value)} />
            </div>
            <div className="mb-3">
                <label className="form-label">Email address</label>
                <input type="email" className="form-control" onChange={(e) => setEmail(e.target.value)} />
                <div
                    className="form-text">We'll never share your email with anyone else.</div>
            </div>
            <button type="submit" className="btn btn-primary" onClick={handleSubmit}>Submit</button>
        </form>
    </div>
}

export default Create;